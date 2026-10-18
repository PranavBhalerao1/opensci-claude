"""Offline before/after numbers for the database traffic of OpenScientist's hot paths.

    cd backend && .venv/Scripts/python.exe scripts/db_traffic_bench.py [--json out.json] [--seconds 30]

Loads a copy of a real research run (tests/fixtures/egress: 14 tasks, 326 usage rows, 48 papers)
into a throwaway SQLite database and measures statements, rows and bytes fetched for:
one poll of each polled endpoint (as the current frontend calls it), one credit check, 50 agent
events, and a live execution with fake agents. Runs against old and new code alike (unknown query
parameters are ignored by an older backend), so the same script gives the baseline and the result.

It never touches a real database: DATABASE_URL is forced to a temp SQLite file before any app
module is imported, and the script refuses to run otherwise.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp(prefix='os-bench-')) / 'bench.db'}"
os.environ["E2B_API_KEY"] = ""
os.environ["COLAB_CREDENTIALS_FILE"] = ""
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]

from app.db import DATABASE_URL, init_db  # noqa: E402

if not DATABASE_URL.startswith("sqlite:///"):
    sys.exit(f"refusing to run: DATABASE_URL is not SQLite ({DATABASE_URL.split(':', 1)[0]})")
init_db()

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app import beta, jobs  # noqa: E402
from app.auth import CurrentUser, get_current_user  # noqa: E402
from app.db import BetaUser, TaskState, engine  # noqa: E402
from app.execution import orchestrator  # noqa: E402
from app.main import app  # noqa: E402
from traffic import load_study, measure  # noqa: E402


def poll(client: TestClient, path: str, params: dict | None = None) -> dict:
    r = client.get(path, params=params or {})
    r.raise_for_status()
    return r.json()


def endpoint(client: TestClient, path: str, rev_params) -> dict:
    """Measure a poll the way the frontend makes it: the first call learns any revision tokens,
    the measured second call sends them back (an older backend ignores them)."""
    first = poll(client, path, rev_params({}))
    with measure() as t:
        poll(client, path, rev_params(first))
    return t.summary()


class _Sandbox:
    capabilities = {"python", "shell", "files", "cpu", "cuda_gpu"}
    secrets: dict = {}

    async def ensure(self):
        pass

    async def install(self, packages):
        return type("Result", (), {"exit_code": 0, "stderr": ""})()

    def stop_all(self):
        pass


def execution(study, seconds: float) -> dict:
    """A live execution: 4 tasks run in parallel for `seconds`, each agent logging an event every
    2 s (a tool call), then finishing. Measures everything the scheduler and agents read."""
    tasks = list(study.state_ids)[:4]
    with Session(engine) as s:
        for tid, sid in study.state_ids.items():
            st = s.get(TaskState, sid)
            st.status = "pending" if tid in tasks else "done"
            s.add(st)
        s.commit()

    async def fake_execute(project_id, mp, task, state_id, policy, http):
        attempt = getattr(orchestrator, "_attempt", None)  # the write-through event log, where it exists
        ctx = attempt(state_id) if attempt else None
        if ctx:
            ctx.__enter__()
        try:
            orchestrator._update(state_id, status="running")
            t0 = time.monotonic()
            step = 0
            while time.monotonic() - t0 < seconds:
                await asyncio.sleep(2)
                step += 1
                orchestrator._append_event(state_id, {"type": "tool", "step": step, "tool": "run_shell",
                                                      "args": "python train.py --epochs 3" * 6, "cost": 0.01,
                                                      "result": "epoch 1 loss 0.42 acc 0.88\n" * 12})
            orchestrator._update(state_id, status="done", summary="Done.")
        finally:
            if ctx:
                ctx.__exit__(None, None, None)

    orchestrator.sandbox_for = lambda pid: _Sandbox()
    orchestrator._write_context = lambda pid, sb: None
    orchestrator.load_secrets = lambda pid: None
    orchestrator._execute = fake_execute
    with measure() as t:
        t0 = time.monotonic()
        asyncio.run(orchestrator.run(study.project_id, jobs.RunHandle(study.execute_run_id)))
        elapsed = time.monotonic() - t0
    return {**t.summary(), "seconds": round(elapsed, 1), "events": len(tasks) * int(seconds // 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write the results here")
    ap.add_argument("--seconds", type=float, default=30.0, help="length of each fake task")
    args = ap.parse_args()

    study = load_study()
    with Session(engine) as s:
        s.merge(BetaUser(user_id=study.user_id, approved=True))
        s.commit()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=study.user_id, email=None)
    client = TestClient(app)
    pid = study.project_id

    def project_rev(d):
        return {"project_rev": d["project_rev"]} if d.get("project_rev") else {}

    out = {
        "GET /execution (2 s poll)": endpoint(client, f"/api/projects/{pid}/execution",
                                              lambda d: {"lite": 1, **project_rev(d)}),
        "GET /usage (15 s poll)": endpoint(client, f"/api/projects/{pid}/usage", lambda d: {}),
        "GET /literature (2 s poll)": endpoint(client, f"/api/projects/{pid}/literature",
                                               lambda d: {"papers_rev": d["papers_rev"]} if d.get("papers_rev") else {}),
        "GET /blueprint (3 s poll)": endpoint(client, f"/api/projects/{pid}/blueprint", project_rev),
        "GET /report (3 s poll)": endpoint(client, f"/api/projects/{pid}/report", project_rev),
        "GET /api/projects (sidebar)": endpoint(client, "/api/projects", lambda d: {"summary": 1}),
        "GET /api/me (30 s poll)": endpoint(client, "/api/me", lambda d: {}),
    }
    with measure() as t:
        beta.project_allowance(pid)
    out["credit check (every agent step)"] = t.summary()

    sid = next(iter(study.state_ids.values()))
    attempt = getattr(orchestrator, "_attempt", None)
    with measure() as t:
        ctx = attempt(sid) if attempt else None
        if ctx:
            ctx.__enter__()
        for i in range(50):
            orchestrator._append_event(sid, {"type": "tool", "step": i, "tool": "run_shell", "args": "x" * 300,
                                             "result": "y" * 500, "cost": 0.0})
        if ctx:
            ctx.__exit__(None, None, None)
    out["50 agent events (one task)"] = t.summary()

    out[f"live execution: 4 tasks x {args.seconds:.0f} s"] = execution(study, args.seconds)

    width = max(len(k) for k in out)
    print(f"{'':{width}}  {'stmts':>6} {'selects':>7} {'rows':>7} {'KB read':>9}")
    for k, v in out.items():
        print(f"{k:{width}}  {v['statements']:>6} {v['selects']:>7} {v['rows']:>7} {v['kb']:>9}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
