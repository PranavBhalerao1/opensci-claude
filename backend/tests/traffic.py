"""Measures database traffic offline: statements, rows and bytes the app fetches from the DB.

Supabase bills egress (bytes sent from Postgres to the app), so the number that matters is what
each request or scheduler step *reads*. Against the offline SQLite database this counts every
value fetched through the DBAPI cursor (text and blobs by length, numbers as 8 bytes), which tracks
Postgres' text wire format closely enough to compare code paths before and after a change.

Used by tests/test_db_traffic.py (regression guards) and scripts/db_traffic_bench.py (before/after
numbers). Both run on SQLite only: never point this at a real database.
"""

import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session

from app.db import GpuUsage, Paper, Project, ProjectPaper, Run, TaskState, Usage, engine

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "egress"

_lock = threading.Lock()
_active: list["Traffic"] = []


def _size(value) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    return 8


def _tally(rows: list) -> None:
    if not _active:
        return
    n, b = len(rows), sum(_size(v) for row in rows for v in row)
    with _lock:
        for t in _active:
            t.rows += n
            t.bytes += b


class _CountingCursor(sqlite3.Cursor):
    def fetchone(self):
        row = super().fetchone()
        if row is not None:
            _tally([row])
        return row

    def fetchmany(self, size=None):
        rows = super().fetchmany(self.arraysize if size is None else size)
        _tally(rows)
        return rows

    def fetchall(self):
        rows = super().fetchall()
        _tally(rows)
        return rows


class _CountingConnection(sqlite3.Connection):
    def cursor(self, factory=None):
        return super().cursor(factory or _CountingCursor)


@dataclass
class Traffic:
    """What the app read from the database inside one `measure()` block."""

    statements: list[str] = field(default_factory=list)
    rows: int = 0
    bytes: int = 0

    @property
    def selects(self) -> list[str]:
        return [s for s in self.statements if s.lstrip().upper().startswith(("SELECT", "WITH"))]

    def selected(self, table: str, column: str) -> bool:
        """True if any SELECT fetched the value of `table.column` (SQLAlchemy always qualifies
        selected columns). A column only passed to a function, like json_array_length(...), is
        computed in the database and does not count."""
        pattern = re.compile(rf"(?<![(\w]){re.escape(table)}\.{re.escape(column)}(?!\w)")
        return any(pattern.search(re.split(r"\sFROM\s", s, maxsplit=1)[0]) for s in self.selects)

    def summary(self) -> dict:
        return {"statements": len(self.statements), "selects": len(self.selects), "rows": self.rows,
                "kb": round(self.bytes / 1024, 1)}


def _before_execute(conn, cursor, statement, parameters, context, executemany):
    if _active:
        with _lock:
            for t in _active:
                t.statements.append(statement)


def _do_connect(dialect, conn_rec, cargs, cparams):
    cparams["factory"] = _CountingConnection


_installed = False


def install() -> None:
    """Route the (SQLite) engine's connections through the counting cursor. Idempotent."""
    global _installed
    if _installed:
        return
    if engine.dialect.name != "sqlite":
        raise RuntimeError("traffic measurement runs on the offline SQLite database only")
    event.listen(engine, "do_connect", _do_connect)
    event.listen(engine, "before_cursor_execute", _before_execute)
    engine.dispose()  # existing pooled connections predate the counting factory
    _installed = True


@contextmanager
def measure():
    install()
    t = Traffic()
    with _lock:
        _active.append(t)
    try:
        yield t
    finally:
        with _lock:
            _active.remove(t)


# ── The e2e study fixture ──────────────────────────────────────────────────


def _load(name: str):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def _dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _new() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Study:
    project_id: str
    user_id: str
    blueprint_run_id: str
    execute_run_id: str
    state_ids: dict[str, str]  # task_id -> TaskState.id


def load_study(user_id: str | None = None) -> Study:
    """Insert a copy of the e2e research run (14 tasks, 326 usage rows, 48 included papers) under
    fresh ids, so tests can load it as often as they like into the shared test database."""
    user_id = user_id or str(uuid.uuid4())
    p = _load("project.json")
    runs = _load("runs.json")
    run_ids = {r["id"]: _new() for r in runs}
    pid = _new()
    with Session(engine) as s:
        s.add(Project(
            id=pid, user_id=user_id, title=p["title"], stage="executed", autonomous=p["autonomous"],
            settings=p["settings"], brief=p["brief"], chosen_gap=p["chosen_gap"], plan=p["plan"],
            blueprint={**p["blueprint"], "run_id": run_ids[p["blueprint"]["run_id"]]}, review=p["review"],
        ))
        for r in runs:
            s.add(Run(**{**r, "id": run_ids[r["id"]], "project_id": pid,
                         "started_at": _dt(r["started_at"]), "finished_at": _dt(r["finished_at"])}))
        states = {}
        for st in _load("task_states.json"):
            sid = _new()
            states[st["task_id"]] = sid
            s.add(TaskState(**{**st, "id": sid, "project_id": pid, "blueprint_run_id": run_ids[st["blueprint_run_id"]],
                               "started_at": _dt(st["started_at"]), "finished_at": _dt(st["finished_at"])}))
        for u in _load("usage.json"):
            s.add(Usage(**{**u, "id": _new(), "project_id": pid, "user_id": user_id,
                           "run_id": run_ids.get(u["run_id"]), "created_at": _dt(u["created_at"])}))
        for g in _load("gpu_usage.json"):
            s.add(GpuUsage(**{**g, "id": _new(), "project_id": pid, "user_id": user_id,
                              "run_id": run_ids.get(g["run_id"]), "created_at": _dt(g["created_at"])}))
        link = {"origin", "score", "relevance", "reason", "included"}
        for row in _load("papers.json"):
            paper_id = _new()
            s.add(Paper(**{k: v for k, v in row.items() if k not in link and k != "updated_at"} | {"id": paper_id}))
            s.add(ProjectPaper(project_id=pid, paper_id=paper_id, **{k: row[k] for k in link}))
        s.commit()
    executes = [r for r in runs if r["kind"] == "execute"]
    return Study(pid, user_id, run_ids[p["blueprint"]["run_id"]], run_ids[executes[-1]["id"]], states)
