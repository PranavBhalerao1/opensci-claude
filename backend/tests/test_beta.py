"""Private beta: access gate, per-user spending cap, and cost attribution (app/beta.py)."""

import asyncio
import math
import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import beta, jobs
from app.auth import CurrentUser, get_current_user
from app.db import BetaUser, GpuUsage, Project, Run, Subscription, TaskState, Usage, engine
from app.execution import colab_runner, orchestrator
from app.execution.sandbox import Sandbox
from app.main import app

REAL_VERIFY = orchestrator._verify

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

    async def fake_execute(project_id, mp, task, state_id, policy, http):
        launched.append(task["id"])
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


@pytest.mark.parametrize("cap,spent", [(None, 0.0), (100.0, 1.0), (1.0, 0.4)])
def test_execution_runs_while_credits_remain(fake_execution, cap, spent):
    """No per-task dollar share is handed out: tasks run whenever the owner has credit left."""
    uid = _user(cap=cap)
    _spend(uid, llm=spent)
    pid, run_id = _execution_project(uid)
    result = asyncio.run(orchestrator.run(pid, jobs.RunHandle(run_id)))
    assert fake_execution == ["T1", "T2"] and result["counts"]["done"] == 2
    assert orchestrator.current_budget(pid) == 15.0  # the project's own budget setting is untouched


def test_execution_still_pauses_at_the_project_budget(fake_execution):
    uid = _user(cap=None)
    pid, run_id = _execution_project(uid)
    with Session(engine) as s:  # the user-set project budget is already spent by this execution
        s.add(Usage(project_id=pid, user_id=uid, run_id=run_id, model="m", cost=15.0))
        s.commit()

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
        await task
        return reason

    assert asyncio.run(scenario()) == "budget: $15.00 of $15.00 spent" and fake_execution == []


# ── Task execution without per-task dollar caps ────────────────────────────


class _TaskSandbox(_FakeSandbox, Sandbox):  # Sandbox: the real fence/stale bookkeeping on local files
    def __init__(self, root: Path):
        self.root = root

    def path(self, rel: str) -> Path:
        return self.root / rel

    async def pull(self):
        pass


@pytest.fixture
def task_env(monkeypatch, tmp_path):
    """One real task state (T1 of the test blueprint) run by _execute with run_agent and
    the verifier faked. Script `agent` with AgentResults; `seen` records each call."""
    from app.execution.agent import AgentResult

    uid = _user(cap=None)
    pid, _ = _execution_project(uid)
    with Session(engine) as s:
        bp_run_id = s.get(Project, pid).blueprint["run_id"]
        mp = s.get(Run, bp_run_id).result["master_plan"]
    orchestrator.prepare_states(pid, bp_run_id, mp)
    with Session(engine) as s:
        state_id = s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id,
                                                  TaskState.task_id == "T1")).one().id
    env = SimpleNamespace(uid=uid, pid=pid, mp=mp, task=mp["tasks"][0], state_id=state_id, root=tmp_path,
                          agent=[], seen=[], verified=[], write=False, Result=AgentResult)

    async def fake_run_agent(spec, prompt, ctx, on_event=None):
        env.seen.append((spec, prompt))
        if env.write:  # written during this attempt, so it is not stale
            env.write = False
            (env.root / "data").mkdir(exist_ok=True)
            (env.root / "data" / "a.csv").write_text("x\n1\n")
        return env.agent.pop(0)

    async def fake_verify(task, sandbox, policy, report=None, amendments=None, leftovers=None):
        env.verified.append(task["id"])
        return [{"check": c, "passed": True, "reason": "ok"} for c in task["acceptance_checks"]]

    monkeypatch.setattr(orchestrator, "sandbox_for", lambda p: _TaskSandbox(tmp_path))
    monkeypatch.setattr(orchestrator, "run_agent", fake_run_agent)
    monkeypatch.setattr(orchestrator, "_verify", fake_verify)
    return env


def _run_task(env) -> TaskState:
    async def go():
        async with httpx.AsyncClient() as http:
            await orchestrator._execute(env.pid, env.mp, env.task, env.state_id, "default", http)

    asyncio.run(go())
    with Session(engine) as s:
        return s.get(TaskState, env.state_id)


def _write_output(env) -> None:
    """The next agent run writes the task's output (output already there beforehand would be stale)."""
    env.write = True


def test_task_spec_has_no_dollar_cap_and_keeps_step_limit(task_env):
    env = task_env
    env.task["max_cost_usd"] = 0.05  # a tiny planner estimate no longer limits anything
    _write_output(env)
    env.agent.append(env.Result("success", "done", cost=3.75))  # far past the old $0.05 cap
    st = _run_task(env)
    spec, _ = env.seen[0]
    assert not hasattr(spec, "max_cost") and spec.max_steps == orchestrator.MAX_AGENT_STEPS
    assert (st.status, st.attempts, st.cost) == ("done", 1, pytest.approx(3.75))


def test_credit_limit_requeues_task_without_using_a_retry(task_env):
    env = task_env
    env.agent.append(env.Result("credit_limit", beta.LIMIT_MESSAGE, steps=3, cost=1.5))
    st = _run_task(env)
    assert (st.status, st.attempts, st.cost) == ("pending", 0, pytest.approx(1.5))
    assert env.verified == []  # no verifier call is spent on an interrupted task
    assert st.events[-1]["text"] == "Stopped: beta usage limit reached"


def test_verifier_refused_for_credit_requeues_task_instead_of_failing(task_env, monkeypatch):
    """The verifier goes through llm.parse, which refuses once credits are gone."""
    from app import llm

    env = task_env
    _set_cap(env.uid, 1.0)
    _spend(env.uid, llm=1.0)  # the agent's last step used up the allowance
    monkeypatch.setattr(orchestrator, "_verify", REAL_VERIFY)
    _write_output(env)
    env.agent.append(env.Result("success", "done", cost=0.7))
    token = llm.current_project.set(env.pid)
    try:
        st = _run_task(env)
    finally:
        llm.current_project.reset(token)
    assert (st.status, st.attempts, st.cost) == ("pending", 0, pytest.approx(0.7))
    assert st.events[-1]["text"] == "Stopped: beta usage limit reached"


def test_retry_with_feedback_still_works(task_env, monkeypatch):
    env = task_env
    for tier, name in (("reasoning", "gpt-6-astra"), ("standard", "gpt-6-sol"), ("bulk", "gpt-6-luna")):
        monkeypatch.setattr(orchestrator.settings, f"model_{tier}", name)
    env.agent.append(env.Result("failed", "Source returned 404", issues=["dataset URL dead"], cost=0.4))
    st = _run_task(env)
    assert (st.status, st.attempts) == ("pending", 1)  # retries=1 in the test blueprint
    assert "Source returned 404" in st.note and "dataset URL dead" in st.note
    assert env.verified == []  # an explicit "failed" report is trusted

    _write_output(env)
    env.agent.append(env.Result("success", "fixed", cost=0.6))
    st = _run_task(env)
    (spec1, _), (spec2, prompt2) = env.seen
    assert "PREVIOUS ATTEMPT FAILED" in prompt2 and "dataset URL dead" in prompt2
    assert (spec1.model, spec2.model) == ("gpt-6-sol", "gpt-6-astra")  # tier escalation is unchanged
    assert (st.status, st.attempts, st.cost) == ("done", 2, pytest.approx(1.0))


def test_credit_limit_on_a_retry_keeps_the_feedback(task_env):
    env = task_env
    env.agent += [env.Result("failed", "Source returned 404", issues=["dataset URL dead"], cost=0.4),
                  env.Result("credit_limit", beta.LIMIT_MESSAGE, cost=0.3),
                  env.Result("failed", "still broken", cost=0.1)]
    _run_task(env)
    st = _run_task(env)  # interrupted by the credit limit: still attempt 1, feedback intact
    assert (st.status, st.attempts) == ("pending", 1) and "dataset URL dead" in st.note
    st = _run_task(env)  # after the cap is raised and execution resumes
    assert "dataset URL dead" in env.seen[2][1]
    assert (st.status, st.attempts, st.cost) == ("failed", 2, pytest.approx(0.8))


def test_retries_are_still_limited(task_env):
    env = task_env
    env.agent += [env.Result("step_limit", "Stopped after 80 steps.", cost=0.2) for _ in range(2)]
    assert _run_task(env).status == "pending"
    st = _run_task(env)
    assert (st.status, st.attempts) == ("failed", 2)
    assert "Missing outputs: data/a.csv" in st.note


def test_step_limited_agent_with_verified_outputs_is_done(task_env):
    env = task_env
    _write_output(env)
    env.agent.append(env.Result("step_limit", "Stopped after 80 steps.", cost=0.2))
    st = _run_task(env)
    assert st.status == "done" and env.verified == ["T1"]
    assert any("step_limit" in i for i in st.issues)


def test_subagents_have_no_dollar_cap_and_report_credit_limit(task_env):
    from app.execution.agent import AgentSpec
    from app.execution.tools import ToolContext

    env = task_env
    env.agent += [env.Result("success", "half 1", cost=2.0), env.Result("credit_limit", beta.LIMIT_MESSAGE, cost=0.5)]
    parent = AgentSpec(name="P", instructions="i", model="m", tools=["run_python", "spawn_subagents"])
    ctx = ToolContext(env.pid, _TaskSandbox(env.root), None)
    cost = [0.0]
    spawn = orchestrator._subagent_runner(parent, ctx, env.state_id, cost)
    out = asyncio.run(spawn([{"name": "a", "instructions": "x", "outputs": []},
                             {"name": "b", "instructions": "y", "outputs": []}]))
    assert sorted(o["status"] for o in out) == ["credit_limit", "success"] and cost[0] == pytest.approx(2.5)
    assert len(env.seen) == 2
    for spec, _ in env.seen:
        assert not hasattr(spec, "max_cost") and spec.max_steps == orchestrator.MAX_AGENT_STEPS
        assert "spawn_subagents" not in spec.tools


@pytest.mark.parametrize("cap,spent,expected", [(None, 0.0, 10.0), (100.0, 1.0, 10.0), (3.0, 1.0, 2.0)])
def test_gpu_budget_respects_allowance(cap, spent, expected):
    uid = _user(cap=cap)
    _spend(uid, llm=spent)
    pid = _project(uid, settings={"gpu_budget_usd": 10.0})
    _spend(uid, gpu=0.25, project_id=pid)  # GPU spend counts toward the cap and toward the project
    assert colab_runner.gpu_budget(pid) == pytest.approx(expected)


# ── Paid plans ─────────────────────────────────────────────────────────────


def _subscribe(uid: str, credits: float = 40.0, status: str = "active", started_days_ago: float = 1.0,
               plan: str = "light") -> None:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=started_days_ago)
    with Session(engine) as s:
        sub = s.get(Subscription, uid) or Subscription(user_id=uid, plan=plan, status=status)
        sub.plan, sub.status, sub.credits_usd = plan, status, credits
        sub.period_start, sub.period_end = start, start + timedelta(days=30)
        s.add(sub)
        s.commit()


def test_a_paid_plan_grants_access_without_beta_approval():
    for uid in (_user(approved=None), _user(approved=False)):
        _subscribe(uid, credits=40.0)
        with _client(uid) as client:
            assert client.get("/api/projects").status_code == 200
            me = client.get("/api/me").json()
        assert me == {**me, "beta_approved": True, "unlimited": False, "cap_usd": 40.0, "spent_usd": 0.0,
                      "remaining_usd": 40.0, "plan": "light"}
        assert me["period_end"]


def test_plan_credits_count_only_this_periods_spend():
    uid = _user(approved=None)
    _subscribe(uid, credits=40.0, started_days_ago=1)
    with Session(engine) as s:  # spent in an earlier period: does not count
        s.add(Usage(user_id=uid, model="m", cost=100.0, created_at=datetime.now(timezone.utc) - timedelta(days=5)))
        s.commit()
    _spend(uid, llm=10.0, gpu=2.5)
    assert beta.get_user_remaining(uid) == pytest.approx(27.5)
    _subscribe(uid, credits=40.0, started_days_ago=0)  # renewal: a fresh period
    assert beta.get_user_remaining(uid) == pytest.approx(40.0)


def test_plan_replaces_a_beta_cap_but_not_unlimited_team_access():
    capped = _user(approved=True, cap=5.0)
    _spend(capped, llm=5.0)
    assert beta.get_user_remaining(capped) == 0
    _subscribe(capped, credits=175.0, plan="intensive", started_days_ago=0)
    assert beta.get_user_remaining(capped) == pytest.approx(175.0)
    team = _user(approved=True, cap=None)
    _subscribe(team, credits=40.0)
    _spend(team, llm=500.0)
    assert beta.get_user_remaining(team) == math.inf and beta.status(team)["plan"] == "light"


def test_lapsed_or_cancelled_plans_stop_access():
    for status, days in (("canceled", 1), ("past_due", 1), ("incomplete", 1), ("active", 33)):
        uid = _user(approved=None)
        _subscribe(uid, status=status, started_days_ago=days)  # 33 days: ended 3 days ago, past the grace
        assert beta.get_plan(uid) is None and beta.get_user_remaining(uid) == 0
        with _client(uid) as client:
            assert _code(client.get("/api/projects")) == "beta_pending"
    uid = _user(approved=None)
    _subscribe(uid, started_days_ago=31)  # ended a day ago: renewal webhook may still be on its way
    assert beta.get_plan(uid) is not None


def test_a_plan_out_of_credits_hits_the_limit():
    uid = _user(approved=None)
    _subscribe(uid, credits=1.0)
    _spend(uid, llm=1.0)
    pid = _project(uid)
    with _client(uid) as client:
        r = client.post(f"/api/projects/{pid}/messages", json={"content": "hi"})
    assert r.status_code == 403 and _code(r) == "beta_limit_reached"
