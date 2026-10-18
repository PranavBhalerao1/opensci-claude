"""Lightweight database traffic counters, for watching egress in production.

Counts statements (grouped by their SQL with literals already parameterised away by SQLAlchemy),
rows the database returned, new connections and invalidated ones. With DB_STATS_LOG_SECONDS set,
a summary is logged at that interval (Heroku logs); otherwise nothing is logged. Nothing here is
exposed over HTTP.

Rows come from the DBAPI cursor's rowcount after execute, which psycopg reports for SELECTs (the
offline sqlite3 driver reports -1, so rows read 0 there; tests/traffic.py measures bytes offline).
"""

import logging
import os
import re
import threading
import time
from collections import Counter

from sqlalchemy import event
from sqlalchemy.engine import Engine

log = logging.getLogger("openscientist.dbstats")

_lock = threading.Lock()
_statements: Counter[str] = Counter()
_rows: Counter[str] = Counter()
_counters: Counter[str] = Counter()
_since = time.monotonic()


def _shape(statement: str) -> str:
    """A short, stable label: the verb and the tables it touches."""
    s = " ".join(statement.split())
    verb = s.split(" ", 1)[0].upper()
    tables = sorted(set(re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+\"?(\w+)", s, re.IGNORECASE)))
    return f"{verb} {','.join(tables) or '-'}"


def _after_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    shape = _shape(statement)
    rows = getattr(cursor, "rowcount", -1)
    with _lock:
        _statements[shape] += 1
        if shape.startswith("SELECT") and rows and rows > 0:
            _rows[shape] += rows


def _on_connect(dbapi_conn, record) -> None:
    with _lock:
        _counters["connections_opened"] += 1


def _on_invalidate(dbapi_conn, record, exc) -> None:
    with _lock:
        _counters["connections_invalidated"] += 1


def snapshot(reset: bool = False) -> dict:
    global _since
    with _lock:
        out = {
            "seconds": round(time.monotonic() - _since, 1),
            "statements": dict(_statements.most_common()),
            "rows": dict(_rows.most_common()),
            **_counters,
        }
        if reset:
            _statements.clear()
            _rows.clear()
            _counters.clear()
            _since = time.monotonic()
    return out


def _reporter(interval: float) -> None:
    while True:
        time.sleep(interval)
        snap = snapshot(reset=True)
        total = sum(snap["statements"].values())
        top = ", ".join(f"{k}={v}" for k, v in list(snap["statements"].items())[:8])
        log.warning(
            "db stats over %ss: %d statements, %d rows, %d new connections, %d invalidated | %s",
            snap["seconds"], total, sum(snap["rows"].values()), snap.get("connections_opened", 0),
            snap.get("connections_invalidated", 0), top,
        )


_installed = False


def install(engine: Engine) -> None:
    global _installed
    if _installed:
        return
    _installed = True
    event.listen(engine, "after_cursor_execute", _after_execute)
    event.listen(engine.pool, "connect", _on_connect)
    event.listen(engine.pool, "invalidate", _on_invalidate)
    try:
        interval = float(os.environ.get("DB_STATS_LOG_SECONDS") or 0)
    except ValueError:
        interval = 0
    if interval > 0:
        threading.Thread(target=_reporter, args=(interval,), name="db-stats", daemon=True).start()
