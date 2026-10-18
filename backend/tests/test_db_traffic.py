"""Database traffic guards: the polled routes and the execution scheduler must not re-read large
rows (task event logs, the project's plan and review, blueprint results) on every tick.

Supabase bills what Postgres sends back, and these paths run every few seconds for as long as a
page is open or a run is live. Measured on a copy of a real research run (tests/traffic.py); the
byte limits are a few times the measured figures, far below what these paths read before (see
scripts/db_traffic_bench.py for the before/after numbers)."""

import asyncio
import copy
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import beta, jobs
from app.auth import CurrentUser, get_current_user
from app.db import BetaUser, Project, Run, TaskState, engine
from app.execution import orchestrator
from app.execution.sandbox import SandboxUnreachable
from app.main import app
from traffic import load_study, measure

KB = 1024


@pytest.fixture
def study():
    st = load_study()
    with Session(engine) as s:
        s.merge(BetaUser(user_id=st.user_id, approved=True))
        s.commit()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=st.user_id, email=None)
    yield st
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(study):
    return TestClient(app)


def _get(client, path, **params):
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── Polled routes ──────────────────────────────────────────────────────────


def test_execution_poll_leaves_out_logs_plan_and_blueprint(client, study):
    path = f"/api/projects/{study.project_id}/execution"
    first = _get(client, path, lite=1)
    assert first["project"]["id"] == study.project_id and first["project_rev"]
    with measure() as t:
        d = _get(client, path, lite=1, project_rev=first["project_rev"])
    assert d["project"] is None and d["project_rev"] == first["project_rev"]
    assert not t.selected("task_states", "events")
    assert not any(t.selected("projects", c) for c in ("plan", "brief", "chosen_gap", "review"))
    assert not any("runs.result" in s and "runs.id =" in s for s in t.selects)  # no blueprint read
    assert t.bytes < 64 * KB, t.summary()
    # The fixture's 14 tasks with every field the UI shows except the log, which is counted.
    with Session(engine) as s:
        stored = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.project_id == study.project_id))}
    assert len(d["tasks"]) == 14
    for task in d["tasks"]:
        st = stored[task["task_id"]]
        assert task["events"] == [] and task["event_count"] == len(st.events) == task["event_seq"]
        assert task["summary"] == st.summary and task["checks"] == st.checks and task["status"] == st.status


def test_execution_poll_without_lite_is_unchanged(client, study):
    d = _get(client, f"/api/projects/{study.project_id}/execution")
    assert d["project"]["plan"] and all("events" in t and "event_count" not in t for t in d["tasks"])
    assert sum(len(t["events"]) for t in d["tasks"]) > 0


def test_task_log_is_fetched_on_demand(client, study):
    tid = next(iter(study.state_ids))
    d = _get(client, f"/api/projects/{study.project_id}/execution/tasks/{tid}/events")
    with Session(engine) as s:
        events = s.get(TaskState, study.state_ids[tid]).events
    assert d == {"events": events, "event_seq": len(events)}
    assert client.get(f"/api/projects/{study.project_id}/execution/tasks/T9.9/events").status_code == 404


def test_task_log_of_another_users_project_is_hidden(study):
    other = TestClient(app)
    intruder = str(uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=intruder, email=None)
    with Session(engine) as s:
        s.merge(BetaUser(user_id=intruder, approved=True))
        s.commit()
    tid = next(iter(study.state_ids))
    for path in (f"/execution/tasks/{tid}/events", "/execution?lite=1", "/usage", "/literature", "/review"):
        assert other.get(f"/api/projects/{study.project_id}{path}").status_code == 404, path


def test_running_task_carries_its_live_tail(client, study):
    tid, sid = next(iter(study.state_ids.items()))
    orchestrator._update(sid, status="running")
    with orchestrator._attempt(sid):
        for i in range(6):
            orchestrator._append_event(sid, {"type": "tool", "step": i, "tool": "run_shell", "args": f"cmd {i}",
                                             "cost": 0.0})
        d = _get(client, f"/api/projects/{study.project_id}/execution", lite=1)
        task = next(t for t in d["tasks"] if t["task_id"] == tid)
        assert [e["args"] for e in task["events"]] == ["cmd 2", "cmd 3", "cmd 4", "cmd 5"]
        seq = task["event_seq"]
        orchestrator._append_event(sid, {"type": "tool", "step": 6, "tool": "run_shell", "args": "cmd 6", "cost": 0.0})
        d = _get(client, f"/api/projects/{study.project_id}/execution", lite=1)
        assert next(t for t in d["tasks"] if t["task_id"] == tid)["event_seq"] == seq + 1


@pytest.mark.parametrize("route", ["gaps", "plan", "blueprint", "report", "review", "execution"])
def test_unchanged_project_is_not_sent_again(client, study, route):
    path = f"/api/projects/{study.project_id}/{route}"
    first = _get(client, path)
    assert first["project"]["id"] == study.project_id
    with measure() as t:
        same = _get(client, path, project_rev=first["project_rev"])
    assert same["project"] is None and not t.selected("projects", "plan")
    # Any write to the project (here a stage change, as a background job makes) shows up at once.
    with Session(engine) as s:
        p = s.get(Project, study.project_id)
        p.stage = "complete"
        s.add(p)
        s.commit()
    changed = _get(client, path, project_rev=first["project_rev"])
    assert changed["project"]["stage"] == "complete" and changed["project_rev"] != first["project_rev"]


def test_project_revision_ignores_a_stale_token(client, study):
    d = _get(client, f"/api/projects/{study.project_id}/plan", project_rev="20000101T000000.000000")
    assert d["project"]["id"] == study.project_id


def test_usage_poll_is_one_aggregate(client, study):
    with measure() as t:
        d = _get(client, f"/api/projects/{study.project_id}/usage")
    assert d["calls"] == 326 and d["total"] == pytest.approx(sum(d["by_tier"].values()), abs=1e-3)
    assert d["total"] == pytest.approx(11.43, abs=0.01)  # the run's recorded LLM spend
    assert not t.selected("usage", "input_tokens") and not t.selected("projects", "plan")
    assert t.bytes < 4 * KB, t.summary()


def test_literature_poll_resends_papers_only_when_they_change(client, study):
    path = f"/api/projects/{study.project_id}/literature"
    first = _get(client, path)
    assert len(first["papers"]) == 48 and first["papers_rev"]
    assert all("references" not in p and "norm_title" not in p for p in first["papers"])
    with measure() as t:
        same = _get(client, path, papers_rev=first["papers_rev"])
    assert same["papers"] is None and same["run"]["id"] == first["run"]["id"]
    assert not t.selected("papers", "abstract") and t.bytes < 24 * KB, t.summary()
    # A rerun replaces the project's papers: its run is part of the revision even if counts match.
    with Session(engine) as s:
        s.add(Run(project_id=study.project_id, kind="literature", status="running"))
        s.commit()
    rerun = _get(client, path, papers_rev=first["papers_rev"])
    assert rerun["papers"] is not None and rerun["papers_rev"] != first["papers_rev"]


def test_project_list_summary_has_no_project_json(client, study):
    with measure() as t:
        rows = _get(client, "/api/projects", summary=1)
    assert [r["id"] for r in rows] == [study.project_id]
    assert rows[0]["title"] and rows[0]["review"] is None and "plan" not in rows[0]
    assert not any(t.selected("projects", c) for c in ("plan", "brief", "chosen_gap", "settings"))
    with Session(engine) as s:
        p = s.get(Project, study.project_id)
        p.review = {"status": "repairing", "iteration": 3, "stale": False, "iterations": [{"n": 1}] * 50}
        s.add(p)
        s.commit()
    row = _get(client, "/api/projects", summary=1)[0]
    assert row["review"] == {"status": "repairing", "stale": False, "iteration": 3}
    assert "settings" in _get(client, "/api/projects")[0]  # without summary: the full rows, as before


def test_credit_check_is_three_small_queries(study):
    beta.owner_of(study.project_id)  # an owner never changes: remembered after the first lookup
    with measure() as t:
        remaining = beta.project_allowance(study.project_id)
    assert remaining == float("inf")  # approved, uncapped
    assert len(t.selects) == 3 and t.bytes < KB, t.summary()


# ── Event log ──────────────────────────────────────────────────────────────


def test_agent_events_are_written_without_reading_the_row(study):
    sid = next(iter(study.state_ids.values()))
    with Session(engine) as s:
        before = s.get(TaskState, sid).events
    with orchestrator._attempt(sid):
        with measure() as t:
            for i in range(50):
                orchestrator._append_event(sid, {"type": "tool", "step": i, "tool": "run_shell", "args": "x" * 300,
                                                 "cost": 0.0})
    assert t.selects == [] and len(t.statements) == 50
    with Session(engine) as s:
        after = s.get(TaskState, sid).events
    # Earlier attempts' events are kept (the log carries on across attempts), capped as before.
    assert after == [*before, *after[len(before):]][-orchestrator.MAX_EVENTS:]
    assert len(after) == min(len(before) + 50, orchestrator.MAX_EVENTS) and after[-1]["step"] == 49
    assert sid not in orchestrator._live


def test_event_outside_an_attempt_reads_only_the_log(study):
    sid = next(iter(study.state_ids.values()))
    with measure() as t:
        orchestrator._append_event(sid, {"type": "message", "step": 0, "text": "hi", "cost": 0.0})
    assert len(t.selects) == 1 and t.selected("task_states", "events")
    assert not t.selected("task_states", "summary")


def test_live_log_is_dropped_on_every_way_out_of_an_attempt(study, monkeypatch):
    sid = next(iter(study.state_ids.values()))

    async def boom(*args):
        assert sid in orchestrator._live
        raise SandboxUnreachable("gone")

    monkeypatch.setattr(orchestrator, "_run_attempt", boom)
    with pytest.raises(SandboxUnreachable):
        asyncio.run(orchestrator._execute(study.project_id, {}, {}, sid, "default", None))
    assert sid not in orchestrator._live


def test_run_progress_is_written_without_reading_the_run(study):
    h = jobs.RunHandle(study.execute_run_id)
    h.note("first")  # reads the log once
    with measure() as t:
        h.phase("running", "Executing tasks")
        h.note("second")
        h.counts(done=1)
        h.counts(done=1)  # unchanged: not written
        h.phase("paused:x")
    assert t.selects == [] and len(t.statements) == 4
    with Session(engine) as s:
        run = s.get(Run, study.execute_run_id)
    assert [line["text"] for line in run.log][-3:] == ["first", "Executing tasks", "second"]
    assert run.counts["done"] == 1 and run.phase == "paused:x"


# ── Scheduler ──────────────────────────────────────────────────────────────


class _Sandbox:
    capabilities = {"python", "shell", "files", "cpu"}
    secrets: dict = {}

    async def ensure(self):
        pass

    def stop_all(self):
        pass


def _execution(uid: str, human: bool = False, n_tasks: int = 2) -> tuple[str, str]:
    from test_core import _mp

    mp = {**_mp(), "python_packages": []}
    base = mp["tasks"][0]
    mp["tasks"] = [{**copy.deepcopy(base), "id": f"T{i}", "title": f"T{i}", "depends_on": [], "inputs": [],
                    "human_required": human} for i in range(1, n_tasks + 1)]
    with Session(engine) as s:
        p = Project(title="_traffic", user_id=uid, autonomous=True, settings={"budget": {"llm_usd": 15.0}})
        s.add(p)
        s.commit()
        bp = Run(project_id=p.id, kind="blueprint", status="done", result={"master_plan": mp})
        exec_run = Run(project_id=p.id, kind="execute")
        s.add(bp)
        s.add(exec_run)
        s.commit()
        p.blueprint = {"run_id": bp.id}
        s.add(p)
        s.commit()
        return p.id, exec_run.id


@pytest.fixture
def gated(monkeypatch):
    """Fake agents that run until their gate opens (or they are cancelled)."""
    uid = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(BetaUser(user_id=uid, approved=True))
        s.commit()
    gates: dict[str, asyncio.Event] = {}
    started: list[str] = []

    async def fake_execute(project_id, mp, task, state_id, policy, http):
        orchestrator._update(state_id, status="running")
        started.append(task["id"])
        gate = gates.setdefault(task["id"], asyncio.Event())
        await gate.wait()
        orchestrator._update(state_id, status="done")

    monkeypatch.setattr(orchestrator, "sandbox_for", lambda pid: _Sandbox())
    monkeypatch.setattr(orchestrator, "_write_context", lambda pid, sb: None)
    monkeypatch.setattr(orchestrator, "_execute", fake_execute)
    return uid, gates, started


def _reason(pid: str) -> str:
    ctl = orchestrator.control(pid)
    return (ctl.reason or "") if ctl else ""


async def _until(cond, timeout=3.0):
    t0 = time.monotonic()
    while not cond():
        assert time.monotonic() - t0 < timeout, "timed out"
        await asyncio.sleep(0.01)


def test_scheduler_wakes_on_changes_and_a_wake_is_cheap(gated):
    uid, gates, started = gated
    pid, run_id = _execution(uid)

    async def scenario():
        run = asyncio.create_task(orchestrator.run(pid, jobs.RunHandle(run_id)))
        await _until(lambda: len(started) == 2)
        await asyncio.sleep(0.1)  # settled: both tasks running, the scheduler asleep
        with measure() as idle:  # longer than the 5 s tick the scheduler used to poll on
            await asyncio.sleep(5.5)
        with measure() as wake:
            orchestrator.notify(pid)
            await asyncio.sleep(0.3)
        for g in gates.values():
            g.set()
        return idle, wake, await asyncio.wait_for(run, 3)

    idle, wake, result = asyncio.run(scenario())
    assert idle.statements == []  # nothing changed, nothing read: no clock-driven polling
    assert wake.selects, "notify did not wake the scheduler"
    for table, column in (("task_states", "events"), ("task_states", "summary"), ("projects", "plan"),
                          ("runs", "result"), ("runs", "log")):
        assert not wake.selected(table, column), (table, column)
    assert wake.bytes < 2 * KB, wake.summary()
    assert result["counts"]["done"] == 2


def test_cancel_from_a_worker_thread_stops_the_run_promptly(gated):
    uid, gates, started = gated
    pid, run_id = _execution(uid)

    async def scenario():
        run = asyncio.create_task(orchestrator.run(pid, jobs.RunHandle(run_id)))
        await _until(lambda: len(started) == 2)
        t0 = time.monotonic()
        # The cancel route is a sync FastAPI route: it runs in a worker thread.
        threading.Thread(target=orchestrator.control(pid).cancel).start()
        result = await asyncio.wait_for(run, 3)
        return result, time.monotonic() - t0

    result, took = asyncio.run(scenario())
    assert result["cancelled"] and took < 1.0, took


def test_resolving_a_human_task_from_a_worker_thread_wakes_the_run(gated):
    uid, gates, started = gated
    pid, run_id = _execution(uid, human=True, n_tasks=1)

    async def scenario():
        run = asyncio.create_task(orchestrator.run(pid, jobs.RunHandle(run_id)))
        await _until(lambda: _reason(pid).startswith("human"))
        t0 = time.monotonic()
        await asyncio.to_thread(orchestrator.set_task_status, pid, "T1", "done", None)  # the task route
        result = await asyncio.wait_for(run, 3)
        return result, time.monotonic() - t0

    result, took = asyncio.run(scenario())
    assert result["counts"]["done"] == 1 and took < 1.0, took


def test_notify_during_a_network_pause_does_not_cut_the_backoff(gated, monkeypatch):
    uid, gates, started = gated
    pid, run_id = _execution(uid, n_tasks=1)
    monkeypatch.setattr(orchestrator, "NETWORK_RETRY", (30,))

    async def offline(project_id, mp, task, state_id, policy, http):
        raise SandboxUnreachable("offline")

    monkeypatch.setattr(orchestrator, "_execute", offline)

    async def scenario():
        run = asyncio.create_task(orchestrator.run(pid, jobs.RunHandle(run_id)))
        await _until(lambda: _reason(pid).startswith(orchestrator.NETWORK_PAUSE))
        orchestrator.notify(pid)
        await asyncio.sleep(0.3)
        still = _reason(pid).startswith(orchestrator.NETWORK_PAUSE)
        orchestrator.control(pid).cancel()
        await asyncio.wait_for(run, 3)
        return still

    assert asyncio.run(scenario()), "a notify resumed a network pause before its backoff ended"


def test_review_watcher_reads_only_the_fields_it_checks(study):
    from app import refine

    review = {"status": "repairing", "step": "execute", "started_at": "2026-10-10T04:00:00+00:00", "max_usd": 12,
              "attention": None, "iterations": [{"n": i, "notes": "x" * 2000} for i in range(20)]}
    with Session(engine) as s:
        p = s.get(Project, study.project_id)
        p.review = review
        s.add(p)
        s.commit()
    with measure() as t:
        st = refine._watch_state(study.project_id)
    assert st == {k: review[k] for k in ("status", "step", "started_at", "max_usd", "attention")}
    assert t.bytes < KB, t.summary()
