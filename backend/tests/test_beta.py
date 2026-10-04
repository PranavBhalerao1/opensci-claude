"""Private beta: access gate, per-user spending cap, and cost attribution (app/beta.py)."""

import asyncio
import contextlib
import math
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import beta, jobs
from app.auth import CurrentUser, get_current_user
from app.db import BetaUser, GpuUsage, Project, Run, TaskState, Usage, engine
from app.execution import modal_runner, orchestrator
from app.main import app

MIGRATION = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20261003000000_private_beta.sql").read_text()


def _user(approved: bool | None = True, cap: float | None = None) -> str:
    """A fresh user id; approved=None leaves them without a beta_users row."""
    uid = str(uuid.uuid4())
    if approved is not None:
        with Session(engine) as s:
            s.add(BetaUser(user_id=uid, approved=approved, cap_usd=cap))
            s.commit()
    return uid


def _set_cap(uid: str, cap: float | None) -> None:
    with Session(engine) as s:
        b = s.get(BetaUser, uid)
        b.cap_usd = cap
        s.add(b)
        s.commit()


def _project(uid: str | None, **fields) -> str:
    with Session(engine) as s:
        p = Project(title="_beta_test", user_id=uid, **fields)
        s.add(p)
        s.commit()
        return p.id


def _spend(uid: str, llm: float = 0.0, gpu: float = 0.0, project_id: str | None = None) -> None:
    with Session(engine) as s:
        if llm:
            s.add(Usage(project_id=project_id, user_id=uid, model="gpt-6-sol", cost=llm))
        if gpu:
            s.add(GpuUsage(project_id=project_id, user_id=uid, gpu="L4", job="j", cost=gpu))
        s.commit()


@contextlib.contextmanager
def _client(uid: str):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid, email="beta@example.com")
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _code(r) -> str | None:
    detail = r.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


# ── Access ─────────────────────────────────────────────────────────────────


def test_new_users_are_pending():
    assert BetaUser(user_id=str(uuid.uuid4())).approved is False
    # The signup trigger inserts a row with only the user id, so the defaults apply.
    assert "after insert on auth.users" in MIGRATION
    assert "insert into public.beta_users (user_id) values (new.id)" in MIGRATION
    assert "approved boolean not null default false" in MIGRATION
    for uid in (_user(approved=None), _user(approved=False)):  # no row yet, or an unapproved row
        with _client(uid) as client:
            me = client.get("/api/me").json()
        assert me["beta_approved"] is False and me["unlimited"] is False


def test_pending_users_cannot_use_the_product():
    uid = _user(approved=False)
    pid = _project(uid)
    with _client(uid) as client:
        for r in (client.get("/api/projects"), client.post("/api/projects", json={}),
                  client.get(f"/api/projects/{pid}"), client.post(f"/api/projects/{pid}/literature/run")):
            assert r.status_code == 403 and _code(r) == "beta_pending"
        assert client.get("/api/me").status_code == 200


def test_unauthenticated_still_gets_401():
    with TestClient(app) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/projects").status_code == 401


def test_approved_users_use_the_product_and_approval_is_live():
    uid = _user(approved=False)
    with _client(uid) as client:
        assert client.get("/api/projects").status_code == 403
        with Session(engine) as s:  # the admin flips the flag in the table editor
            b = s.get(BetaUser, uid)
            b.approved = True
            s.add(b)
            s.commit()
        assert client.get("/api/projects").status_code == 200
        assert client.post("/api/projects", json={}).status_code == 200


def test_existing_users_are_not_locked_out():
    # The migration grandfathers every existing account as approved and uncapped...
    assert "select id, true, null from auth.users" in MIGRATION
    # ...and such a user has full, unlimited access.
    uid = _user(approved=True, cap=None)
    _spend(uid, llm=1000.0)
    with _client(uid) as client:
        me = client.get("/api/me").json()
        assert me["beta_approved"] and me["unlimited"] and me["cap_usd"] is None and me["remaining_usd"] is None
        pid = client.post("/api/projects", json={}).json()["id"]
        r = client.post(f"/api/projects/{pid}/execution/start", json={})
        assert r.status_code == 409 and "Approve the blueprint first" in r.text  # past the beta gate


# ── Spend ──────────────────────────────────────────────────────────────────


def test_spend_is_usage_plus_gpu_usage_only():
    uid, other = _user(cap=5.0), _user(cap=5.0)
    _spend(uid, llm=1.25, gpu=0.57)
    _spend(uid, llm=0.0, gpu=0.0)
    _spend(other, llm=9.0, gpu=9.0)
    _spend(None, llm=7.0, gpu=7.0)  # unattributed rows are never charged to anyone
    # There is no E2B cost ledger: the only inputs are the usage and gpu_usage tables.
    assert beta.get_user_spend(uid) == pytest.approx(1.82)
    assert beta.get_user_remaining(uid) == pytest.approx(3.18)
    with _client(uid) as client:
        me = client.get("/api/me").json()
    assert me == {**me, "beta_approved": True, "unlimited": False, "cap_usd": 5.0,
                  "spent_usd": pytest.approx(1.82), "remaining_usd": pytest.approx(3.18)}


def test_usage_is_attributed_and_survives_project_deletion():
    from app import llm

    uid = _user(cap=5.0)
    pid = _project(uid)
    token = llm.current_project.set(pid)
    try:
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100_000, output_tokens=10_000, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0), content=[])
        cost = llm.record_usage(llm.settings.model_standard, response)
    finally:
        llm.current_project.reset(token)
    with Session(engine) as s:
        row = s.exec(select(Usage).where(Usage.project_id == pid)).one()
        assert row.user_id == uid
    _spend(uid, gpu=0.3, project_id=pid)
    assert beta.get_user_spend(uid) == pytest.approx(cost + 0.3)

    with _client(uid) as client:
        assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert beta.get_user_spend(uid) == pytest.approx(cost + 0.3)
    # In Postgres, project deletion now detaches cost rows instead of cascading.
    assert MIGRATION.count("foreign key (project_id) references public.projects (id) on delete set null") == 2


# ── Enforcement at the request boundary ────────────────────────────────────


def test_user_under_cap_can_start_work():
    uid = _user(cap=5.0)
    _spend(uid, llm=4.9)
    pid = _project(uid)
    with _client(uid) as client:
        r = client.post(f"/api/projects/{pid}/execution/start", json={})
    assert r.status_code == 409 and "Approve the blueprint first" in r.text  # gate passed; existing check ran


@pytest.mark.parametrize("spent", [5.0, 6.5])
def test_user_at_or_over_cap_is_rejected(spent):
    uid = _user(cap=5.0)
    _spend(uid, llm=spent - 1.0, gpu=1.0)
    pid = _project(uid, brief={"title": "x"}, stage="literature")
    with _client(uid) as client:
        for path, body in [("execution/start", {}), ("execution/resume", {}), ("messages", {"content": "hi"}),
                           ("literature/run", None), ("brief/confirm", {"depth": "quick"}),
                           ("plan/revise", {"instruction": "x"}), ("report/run", None)]:
            r = client.post(f"/api/projects/{pid}/{path}", json=body)
            assert r.status_code == 403 and _code(r) == "beta_limit_reached", path
        # Reading the product still works; only billable work is refused.
        assert client.get(f"/api/projects/{pid}").status_code == 200
    with Session(engine) as s:  # rejected before any route side effect
        assert s.exec(select(Run).where(Run.project_id == pid)).all() == []


def test_resume_rechecks_allowance():
    uid = _user(cap=1.0)
    _spend(uid, llm=1.0)
    pid = _project(uid)
    ctl = orchestrator.Control()
    ctl.pause(beta.LIMIT_PAUSE)
    orchestrator._controls[pid] = ctl
    try:
        with _client(uid) as client:
            r = client.post(f"/api/projects/{pid}/execution/resume", json={})
            assert r.status_code == 403 and _code(r) == "beta_limit_reached"
            assert not ctl.go.is_set()
            _set_cap(uid, 2.0)  # the admin raises the cap
            r = client.post(f"/api/projects/{pid}/execution/resume", json={})
            assert r.status_code == 200 and ctl.go.is_set()
    finally:
        orchestrator._controls.pop(pid, None)


# ── Enforcement at execution boundaries ────────────────────────────────────


def test_job_start_refuses_when_over_cap():
    """Covers autonomous chaining too: every stage job passes through jobs.start."""
    uid = _user(cap=1.0)
    _spend(uid, llm=1.5)
    pid = _project(uid)
    called = []

    async def job(project_id, h):
        called.append(project_id)
        return {}

    async def scenario():
        run = jobs.start(pid, "gaps", job)
        for _ in range(50):
            await asyncio.sleep(0.02)
            if not jobs.is_running(pid, "gaps"):
                break
        with Session(engine) as s:
            r = s.get(Run, run.id)
            return r.status, r.error

    assert asyncio.run(scenario()) == ("error", beta.LIMIT_MESSAGE)
    assert called == []


def test_concurrent_runs_remain_allowed():
    uid = _user(cap=5.0)
    p1, p2 = _project(uid), _project(uid)

    async def slow(project_id, h):
        await asyncio.sleep(30)
        return {}

    async def scenario():
        jobs.start(p1, "literature", slow)
        jobs.start(p2, "literature", slow)
        jobs.start(p1, "report", slow)
        await asyncio.sleep(0.2)
        live = [jobs.is_running(p1, "literature"), jobs.is_running(p2, "literature"), jobs.is_running(p1, "report")]
        for pid, kind in ((p1, "literature"), (p2, "literature"), (p1, "report")):
            jobs.cancel(pid, kind)
        await asyncio.sleep(0.1)
        return live

    assert asyncio.run(scenario()) == [True, True, True]


class _FakeSandbox:
    capabilities = {"python", "shell", "files", "cpu"}
    secrets: dict = {}

    async def ensure(self):
        pass

    def stop_all(self):
        pass


def _execution_project(uid: str) -> tuple[str, str]:
    from test_core import _mp

    mp = {**_mp(), "python_packages": []}
    pid = _project(uid, autonomous=True, settings={"budget": {"llm_usd": 15.0}})
    with Session(engine) as s:
        bp = Run(project_id=pid, kind="blueprint", status="done", result={"master_plan": mp})
        s.add(bp)
        s.commit()
        p = s.get(Project, pid)
        p.blueprint = {"run_id": bp.id}
        s.add(p)
        exec_run = Run(project_id=pid, kind="execute")
        s.add(exec_run)
        s.commit()
        return pid, exec_run.id


@pytest.fixture
def fake_execution(monkeypatch):
    launched: list[tuple[str, float]] = []

    async def fake_execute(project_id, mp, task, state_id, policy, http, remaining=math.inf):
        launched.append((task["id"], remaining))
        orchestrator._update(state_id, status="done")

    monkeypatch.setattr(orchestrator, "sandbox_for", lambda pid: _FakeSandbox())
    monkeypatch.setattr(orchestrator, "_write_context", lambda pid, sb: None)
    monkeypatch.setattr(orchestrator, "_execute", fake_execute)
    return launched


def test_execution_pauses_with_beta_reason_when_allowance_is_used(fake_execution):
    uid = _user(cap=1.0)
    _spend(uid, llm=1.0)
    pid, run_id = _execution_project(uid)

    async def scenario():
        task = asyncio.create_task(orchestrator.run(pid, jobs.RunHandle(run_id)))
        reason = None
        for _ in range(100):
            await asyncio.sleep(0.02)
            ctl = orchestrator.control(pid)
            if ctl and ctl.reason:
                reason = ctl.reason
                break
        ctl.cancelled = True
        ctl.resume()
        return reason, await task

    reason, result = asyncio.run(scenario())
    assert reason == beta.LIMIT_PAUSE and fake_execution == [] and result["cancelled"]
    with Session(engine) as s:  # task state is persisted normally, nothing fabricated as done
        states = s.exec(select(TaskState).where(TaskState.project_id == pid)).all()
    assert states and all(st.status == "pending" for st in states)


@pytest.mark.parametrize("cap,spent,expected", [
    (None, 0.0, 15.0),   # unlimited: the project budget alone, exactly as before
    (100.0, 1.0, 15.0),  # project budget is tighter
    (1.0, 0.4, 0.6),     # beta allowance is tighter
])
def test_execution_budget_is_min_of_project_budget_and_allowance(fake_execution, cap, spent, expected):
    uid = _user(cap=cap)
    _spend(uid, llm=spent)
    pid, run_id = _execution_project(uid)
    result = asyncio.run(orchestrator.run(pid, jobs.RunHandle(run_id)))
    assert [t for t, _ in fake_execution] == ["T1", "T2"] and result["counts"]["done"] == 2
    assert all(share == pytest.approx(expected) for _, share in fake_execution)
    assert orchestrator.current_budget(pid) == 15.0  # the project's own budget setting is untouched


@pytest.mark.parametrize("cap,spent,expected", [(None, 0.0, 10.0), (100.0, 1.0, 10.0), (3.0, 1.0, 2.0)])
def test_gpu_budget_respects_allowance(cap, spent, expected):
    uid = _user(cap=cap)
    _spend(uid, llm=spent)
    pid = _project(uid, settings={"gpu_budget_usd": 10.0})
    _spend(uid, gpu=0.25, project_id=pid)  # GPU spend counts toward the cap and toward the project
    assert modal_runner.gpu_budget(pid) == pytest.approx(expected)
