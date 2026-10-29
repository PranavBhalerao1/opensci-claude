"""Network and provider failures are not the task's (offline, deterministic: no sleeps, no network).

Regression for a real run: Wi-Fi dropped mid-task. The Bedrock call failed after the SDK's own
retries; cleanup could not reach E2B, so the live sandbox was declared dead and dropped; the task
was marked failed, its attempt used up and its feedback overwritten; a manual Resume was needed.
The invariant: a transient infrastructure failure re-queues the task exactly as it was (attempt
count, feedback, model), keeps the sandbox, and the run waits for the connection. Scientific
failures and genuinely dead sandboxes behave as before.
"""

import asyncio
import types
from datetime import datetime, timezone

import anthropic
import e2b
import httpx
import httpx2
import pytest
from sqlalchemy import func
from sqlmodel import Session, select

from app import llm
from app.db import Project, Run, TaskState, Usage, engine
from app.execution import orchestrator
from app.execution.agent import AgentResult, AgentSpec, run_agent
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.sandbox import SandboxUnreachable
from app.execution.tools import ToolContext
from test_attempts import AGENT_TOOLS, OUT, FakeE2B, _task, env, tool  # noqa: F401 (env is a fixture)

REQUEST = httpx2.Request("POST", "https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke")


def _status(cls, code: int):
    return cls(f"{code}", response=httpx2.Response(code, request=REQUEST), body=None)


BEDROCK_OUTAGES = [
    pytest.param(lambda: anthropic.APIConnectionError(request=REQUEST), id="connection"),
    pytest.param(lambda: anthropic.APITimeoutError(request=REQUEST), id="timeout"),
    pytest.param(lambda: _status(anthropic.ServiceUnavailableError, 503), id="503"),
    pytest.param(lambda: _status(anthropic.RateLimitError, 429), id="429"),
    pytest.param(lambda: _status(anthropic.InternalServerError, 500), id="500"),
    pytest.param(lambda: _status(anthropic.OverloadedError, 529), id="529"),
]


def _offline(fake: FakeE2B) -> None:
    """E2B cannot be reached: every command and the health probe fail at the transport."""

    async def sh(*args, **kw):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    async def is_running():
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    fake.sb._sh, fake.is_running = sh, is_running


def _online(fake: FakeE2B) -> None:
    fake.sb._sh = fake._sh
    del fake.is_running


def _events(state: TaskState) -> list[str]:
    return [e.get("text", "") for e in state.events]


def _usage_rows() -> int:
    with Session(engine) as s:
        return s.exec(select(func.count()).select_from(Usage)).one()


# ── A task attempt (_execute) ──────────────────────────────────────────────


@pytest.mark.parametrize("outage", BEDROCK_OUTAGES)
def test_bedrock_outage_does_not_use_an_attempt_or_lose_feedback(env, monkeypatch, outage):
    models = []
    scripted = orchestrator.run_agent

    async def run_agent(spec, prompt, ctx, on_event=None):
        models.append(spec.model)
        return await scripted(spec, prompt, ctx, on_event)

    monkeypatch.setattr(orchestrator, "run_agent", run_agent)
    env.task["retries"] = 2

    async def fails_check(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def offline(ctx):
        raise outage()

    async def fixed(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "fixed")

    async def scenario():
        env.scripts[:] = [fails_check, offline, fixed]
        env.verdicts[:] = [False, True]
        await env.attempt()  # a scientific failure: uses an attempt, leaves feedback
        before = env.state()
        assert (before.status, before.attempts) == ("pending", 1) and "Check failed" in before.note
        with pytest.raises(type(outage())):
            await env.attempt()
        after = env.state()
        assert (after.status, after.attempts) == ("pending", 1)  # not counted
        assert after.note == before.note and after.issues == before.issues  # feedback kept
        assert any("not counted as an attempt" in t for t in _events(after))
        assert env.sb._sbx is env.fake  # the sandbox was not touched
        await env.attempt()

    asyncio.run(scenario())
    assert (env.state().status, env.state().attempts) == ("done", 2)
    assert "PREVIOUS ATTEMPT FAILED" in env.prompts[1] and env.prompts[2] == env.prompts[1]  # same feedback
    assert models[2] == models[1]  # the resumed attempt is the same attempt: no extra escalation


def test_interrupted_first_attempt_keeps_its_retry(env):
    """retries=1: an outage, then a genuine failure, still leaves the one retry."""

    async def offline(ctx):
        raise anthropic.APIConnectionError(request=REQUEST)

    async def fails_check(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def fixed(ctx):
        await tool(ctx, "write_file", path="src/runner.py", content="v2\n")
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "fixed")

    async def scenario():
        env.scripts[:] = [offline, fails_check, fixed]
        env.verdicts[:] = [False, True]
        with pytest.raises(anthropic.APIConnectionError):
            await env.attempt()
        assert (env.state().status, env.state().attempts, env.state().note) == ("pending", 0, None)
        await env.attempt()
        assert (env.state().status, env.state().attempts) == ("pending", 1)  # the retry is still there
        await env.attempt()

    asyncio.run(scenario())
    assert (env.state().status, env.state().attempts) == ("done", 2)
    assert "PREVIOUS ATTEMPT FAILED" not in env.prompts[1]  # the outage is not feedback


def test_verifier_outage_does_not_use_an_attempt(env, monkeypatch):
    async def verify(*args, **kw):
        raise anthropic.APIConnectionError(request=REQUEST)

    async def works(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done", cost=0.25)

    monkeypatch.setattr(orchestrator, "_verify", verify)
    env.scripts[:] = [works]
    with pytest.raises(anthropic.APIConnectionError):
        asyncio.run(env.attempt())
    st = env.state()
    assert (st.status, st.attempts, st.note) == ("pending", 0, None)
    assert st.cost == pytest.approx(0.25)  # what the agent did spend is still shown


def test_outage_during_the_attempt_keeps_the_sandbox(env):
    """The real run: the model call fails, and cleanup cannot reach E2B either."""

    async def starts_job_then_offline(ctx):
        await tool(ctx, "start_process", name="train", command="python train.py")
        _offline(env.fake)
        raise anthropic.APIConnectionError(request=REQUEST)

    env.scripts[:] = [starts_job_then_offline]
    with pytest.raises(anthropic.APIConnectionError):  # the reap's failure does not mask the cause
        asyncio.run(env.attempt())
    assert env.sb._sbx is env.fake  # not declared dead, not dropped
    assert env.sb.procs["train"] == "running" and env.fake.jobs["train"]["alive"]  # nothing pretended
    assert (env.state().status, env.state().attempts) == ("pending", 0)


def test_unreachable_cleanup_after_a_finished_attempt_still_verifies(env):
    """As before the change: an unconfirmed final reap does not discard a finished attempt's result
    (the next attempt's fence re-checks)."""

    async def works_then_offline(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        _offline(env.fake)
        return AgentResult("success", "done")

    env.scripts[:] = [works_then_offline]
    asyncio.run(env.attempt())
    assert (env.state().status, env.state().attempts) == ("done", 1)
    assert env.sb._sbx is env.fake


def test_unreachable_sandbox_at_the_fence_does_not_start_the_attempt(env):
    async def attempt1(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def attempt2(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def scenario():
        env.scripts[:] = [attempt1, attempt2]
        env.verdicts[:] = [False, True]
        await env.attempt()
        before = env.state()
        _offline(env.fake)
        with pytest.raises(SandboxUnreachable):
            await env.attempt()
        after = env.state()
        assert len(env.scripts) == 1  # the agent never ran: fail closed
        assert (after.status, after.attempts, after.note) == ("pending", 1, before.note)
        assert env.sb._sbx is env.fake
        _online(env.fake)
        await env.attempt()  # connectivity is back: the same task continues

    asyncio.run(scenario())
    assert (env.state().status, env.state().attempts) == ("done", 2)


# ── E2B liveness ───────────────────────────────────────────────────────────


class Remote:
    """The parts of e2b.AsyncSandbox that _alive and _retrying use."""

    def __init__(self, health):
        self.health = health

    async def is_running(self):
        if isinstance(self.health, BaseException):
            raise self.health
        return self.health


def _sandbox(tmp_path, health) -> tuple[E2BSandbox, Remote, list]:
    sb = E2BSandbox("_infra")
    sb.root = tmp_path
    sb._sbx = remote = Remote(health)
    sb.procs = {"train": "running"}
    created = []

    async def ensure():  # what a real recreation would do
        if sb._sbx is None:
            created.append(True)
            sb._sbx = Remote(True)

    sb.ensure = ensure
    return sb, remote, created


@pytest.mark.parametrize("error", [httpx.ConnectError("getaddrinfo failed"), httpx.ReadTimeout("read timed out"),
                                   e2b.TimeoutException("Request timed out"), OSError("Network is unreachable")],
                         ids=["dns", "read-timeout", "e2b-timeout", "oserror"])
def test_unreachable_sandbox_is_not_declared_dead_or_recreated(tmp_path, error):
    sb, remote, created = _sandbox(tmp_path, error)
    calls = []

    async def fn():
        calls.append(True)
        raise httpx.ConnectError("offline")

    assert asyncio.run(sb._alive()) is None  # unknown, not dead
    with pytest.raises(SandboxUnreachable) as caught:
        asyncio.run(sb._retrying(fn))
    assert isinstance(caught.value.__cause__, httpx.ConnectError)
    assert sb._sbx is remote and created == [] and calls == [True]
    assert sb.procs == {"train": "running"}


def test_dead_sandbox_is_still_recreated(tmp_path):
    sb, remote, created = _sandbox(tmp_path, False)  # E2B says it is gone (HTTP 502)
    calls = []

    async def fn():
        calls.append(True)
        if len(calls) == 1:
            raise e2b.TimeoutException("sandbox timeout")
        return "ok"

    assert asyncio.run(sb._alive()) is False
    assert asyncio.run(sb._retrying(fn)) == "ok"
    assert created == [True] and sb._sbx is not remote and calls == [True, True]
    assert sb.procs == {"train": "done"}


def test_live_sandbox_error_is_raised_as_before(tmp_path):
    sb, remote, created = _sandbox(tmp_path, True)

    async def fn():
        raise RuntimeError("Workspace upload to E2B failed: tar error")

    with pytest.raises(RuntimeError, match="tar error") as caught:
        asyncio.run(sb._retrying(fn))
    assert not isinstance(caught.value, SandboxUnreachable)
    assert sb._sbx is remote and created == []


def test_tools_during_an_outage_reuse_the_same_sandbox_afterwards(env):
    ctx = ToolContext(env.pid, env.sb, None, owner="T2.2")

    async def scenario():
        await tool(ctx, "start_process", name="train", command="sleep 1000")
        _offline(env.fake)
        with pytest.raises(SandboxUnreachable):  # the agent loop shows this to the model as a tool error
            await tool(ctx, "run_shell", command="ls")
        with pytest.raises(httpx.ConnectError):  # not "train is not running": unknown is not dead
            await tool(ctx, "stop_process", name="train")
        assert "running" in await tool(ctx, "check_process", name="train")
        _online(env.fake)
        assert "exit_code: 0" in await tool(ctx, "run_shell", command="ls")

    asyncio.run(scenario())
    assert env.sb._sbx is env.fake and env.sb.procs["train"] == "running" and env.fake.jobs["train"]["alive"]


def test_reap_raises_when_unreachable_but_an_unkillable_process_still_fails_closed(env):
    _offline(env.fake)
    with pytest.raises(SandboxUnreachable):
        asyncio.run(env.sb.fence("T2.2", [OUT]))
    _online(env.fake)
    env.fake.kill_fails = True
    ctx = ToolContext(env.pid, env.sb, None, owner="T2.2")
    asyncio.run(tool(ctx, "start_process", name="run", command="sleep 1000"))
    assert not asyncio.run(env.sb.fence("T2.2", [OUT])).clean


# ── Usage: a request that never returned ───────────────────────────────────


def test_failed_model_request_records_no_usage(env, monkeypatch):
    async def create(**kw):
        raise anthropic.APIConnectionError(request=REQUEST)

    monkeypatch.setattr(llm, "client", type("C", (), {"messages": type("M", (), {"create": staticmethod(create)})})())
    before = _usage_rows()
    spec = AgentSpec(name="a", instructions="i", model="m", tools=[])
    with pytest.raises(anthropic.APIConnectionError):
        asyncio.run(run_agent(spec, "task", ToolContext(env.pid, env.sb, None)))
    with pytest.raises(anthropic.APIConnectionError):
        asyncio.run(llm.parse(model="m", instructions="i", messages=[{"role": "user", "content": "x"}],
                              schema=orchestrator.Verdict))
    assert _usage_rows() == before


def test_bedrock_retries_are_the_sdks_own(monkeypatch):
    """A connection failure is retried by the SDK (max_retries), then raised: no extra loop on top."""
    seen = []

    def offline(request):
        seen.append(request.url.path)
        raise httpx2.ConnectError("offline", request=request)

    client = anthropic.AsyncAnthropicBedrock(
        aws_region="us-east-1", aws_access_key="test", aws_secret_key="test", timeout=llm.client.timeout,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(offline)))
    monkeypatch.setattr(client, "_calculate_retry_timeout", lambda *a, **kw: 0)
    monkeypatch.setattr(llm, "client", client)
    before = _usage_rows()
    with pytest.raises(anthropic.APIConnectionError):
        asyncio.run(llm.parse(model="m", instructions="i", messages=[{"role": "user", "content": "x"}],
                              schema=orchestrator.Verdict))
    assert len(seen) == client.max_retries + 1
    assert _usage_rows() == before


# ── The scheduler ──────────────────────────────────────────────────────────


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """T1 → T2 under the real scheduler, with a faked E2B sandbox and scripted agents."""
    sb = E2BSandbox("_infra_chain")
    sb.root = tmp_path
    fake = FakeE2B(sb)
    monkeypatch.setattr(orchestrator, "sandbox_for", lambda pid: sb)
    monkeypatch.setattr(orchestrator, "_write_context", lambda pid, s: None)
    t1 = _task("T1", ("data/a.csv",))
    t2 = {**_task("T2", ("data/b.csv",)), "depends_on": ["T1"]}
    mp = {"title": "t", "summary": "s", "datasets": [], "python_packages": [], "checkpoints": [], "tasks": [t1, t2],
          "agents": [{"id": "A1", "name": "Runner", "model_tier": "standard", "tools": AGENT_TOOLS, "instructions": "i"}]}
    with Session(engine) as s:
        p = Project(title="_infra_chain", autonomous=True, settings={"budget": {"llm_usd": 15.0}})
        s.add(p)
        s.commit()
        bp = Run(project_id=p.id, kind="blueprint", status="done", result={"master_plan": mp})
        s.add(bp)
        s.commit()
        p.blueprint = {"run_id": bp.id}
        s.add(p)
        ex = Run(project_id=p.id, kind="execute")
        s.add(ex)
        s.commit()
        pid, run_id = p.id, ex.id

    class Chain:
        pass

    c = Chain()
    c.pid, c.sb, c.fake, c.calls, c.script = pid, sb, fake, [], {"T1": [], "T2": []}

    async def run_agent(spec, prompt, ctx, on_event=None):
        c.calls.append(ctx.owner)
        return await c.script[ctx.owner].pop(0)(ctx)

    async def verify(task, *args, **kw):
        return [{"check": ch, "passed": True, "reason": "seen"} for ch in task["acceptance_checks"]]

    monkeypatch.setattr(orchestrator, "run_agent", run_agent)
    monkeypatch.setattr(orchestrator, "_verify", verify)
    c.run = lambda: orchestrator.run(pid, orchestrator.RunHandle(run_id))

    def states() -> dict[str, TaskState]:
        with Session(engine) as s:
            return {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.project_id == pid))}

    c.states = states
    return c


def _writes(path: str):
    async def step(ctx):
        await tool(ctx, "write_file", path=path, content="x\n")
        return AgentResult("success", "done")

    return step


def _raises(exc):
    async def step(ctx):
        raise exc

    return step


def test_outage_pauses_and_resumes_by_itself_without_rerunning_done_tasks(chain, monkeypatch):
    monkeypatch.setattr(orchestrator, "NETWORK_RETRY", (0.01,))
    chain.script["T1"] = [_writes("data/a.csv")]
    chain.script["T2"] = [_raises(anthropic.APIConnectionError(request=REQUEST)), _writes("data/b.csv")]
    phases = []
    real_phase = orchestrator.RunHandle.phase
    monkeypatch.setattr(orchestrator.RunHandle, "phase",
                        lambda self, phase, text=None: (phases.append(phase), real_phase(self, phase, text)))
    result = asyncio.run(chain.run())
    assert result["counts"]["done"] == 2 and result["counts"]["failed"] == 0
    assert chain.calls == ["T1", "T2", "T2"]  # T1 ran once; T2 resumed
    st = chain.states()
    assert (st["T1"].attempts, st["T2"].attempts) == (1, 1)  # the interrupted try was not counted
    # The prefix drives the automatic resume; the provider's exception class is not in the reason.
    assert any(p == f"paused:{orchestrator.NETWORK_PAUSE}{llm.MODEL_UNAVAILABLE}" for p in phases)
    assert chain.sb._sbx is chain.fake


def test_long_outage_keeps_retrying_by_itself(chain, monkeypatch):
    """Live regression: an overnight run gave up after ~15 minutes of outage and waited hours for a
    click. Past the listed delays it keeps trying at the last interval."""
    monkeypatch.setattr(orchestrator, "NETWORK_RETRY", (0.01,))
    chain.script["T1"] = [_writes("data/a.csv")]
    down = _raises(_status(anthropic.ServiceUnavailableError, 503))
    chain.script["T2"] = [down, down, down, down, _writes("data/b.csv")]
    result = asyncio.run(chain.run())
    assert result["counts"]["done"] == 2 and chain.calls == ["T1"] + ["T2"] * 5
    assert chain.states()["T2"].attempts == 1


def test_outage_resumes_at_once_on_resume(chain, monkeypatch):
    monkeypatch.setattr(orchestrator, "NETWORK_RETRY", (3600,))
    chain.script["T1"] = [_writes("data/a.csv")]
    chain.script["T2"] = [_raises(_status(anthropic.ServiceUnavailableError, 503)), _writes("data/b.csv")]

    async def scenario():
        run = asyncio.create_task(chain.run())
        ctl = None
        for _ in range(500):
            await asyncio.sleep(0.01)
            ctl = orchestrator.control(chain.pid)
            if ctl and (ctl.reason or "").startswith(orchestrator.NETWORK_PAUSE):
                break
        assert ctl and ctl.reason.startswith(orchestrator.NETWORK_PAUSE), ctl and ctl.reason
        await asyncio.sleep(0.05)
        assert not run.done()  # paused, not finished or failed
        st = chain.states()
        assert (st["T1"].status, st["T2"].status, st["T2"].attempts) == ("done", "pending", 0)
        ctl.resume()  # what the Resume button does for a live run
        return await run

    result = asyncio.run(scenario())
    assert result["counts"]["done"] == 2 and chain.calls == ["T1", "T2", "T2"]


@pytest.mark.parametrize("error", [RuntimeError("model API error"),
                                   _status(anthropic.BadRequestError, 400)], ids=["runtime", "bad-request"])
def test_other_errors_still_fail_the_task(chain, error):
    chain.script["T1"] = [_writes("data/a.csv")]
    chain.script["T2"] = [_raises(error)]
    result = asyncio.run(chain.run())
    st = chain.states()
    assert st["T2"].status == "failed" and st["T2"].note.startswith("Runtime error")
    assert result["counts"]["failed"] == 1 and chain.calls == ["T1", "T2"]


# ── Reattaching after a restart ────────────────────────────────────────────


class _Listing:
    def __init__(self, items):
        self.items, self.has_next = items, False

    async def next_items(self):
        return self.items


def _restartable(tmp_path, monkeypatch, existing: list):
    """A freshly constructed E2BSandbox (as after a backend restart) and a fake E2B API."""
    from app.execution import e2b_sandbox

    monkeypatch.setattr(e2b_sandbox.settings, "e2b_api_key", "test-key")
    calls = {"connect": [], "create": [], "kill": [], "synced": []}

    class API:
        @staticmethod
        def list(query=None, **kw):
            assert query.metadata == {"project_id": "_infra"}
            return _Listing(existing)

        @staticmethod
        async def connect(sandbox_id, **kw):
            calls["connect"].append(sandbox_id)
            return types.SimpleNamespace(sandbox_id=sandbox_id)

        @staticmethod
        async def create(**kw):
            calls["create"].append(kw)
            raise RuntimeError("stop here")  # creation itself is covered elsewhere

        @staticmethod
        async def kill(sandbox_id, **kw):
            calls["kill"].append(sandbox_id)

    monkeypatch.setattr(e2b, "AsyncSandbox", API)
    sb = E2BSandbox("_infra")
    sb.root = tmp_path / "workspace"  # the host copy is gone

    async def sh(cmd, timeout, **kw):
        return types.SimpleNamespace(exit_code=0, stdout="", stderr="")

    async def pull():
        calls["synced"].append("pull")

    async def push():
        calls["synced"].append("push")

    sb._sh, sb._pull, sb._push = sh, pull, push
    return sb, calls


def _info(sandbox_id, minute):
    return types.SimpleNamespace(sandbox_id=sandbox_id, started_at=datetime(2026, 10, 1, 0, minute, tzinfo=timezone.utc))


def test_a_reader_after_a_restart_restores_the_workspace_from_the_projects_sandbox(tmp_path, monkeypatch):
    sb, calls = _restartable(tmp_path, monkeypatch, [_info("old", 1), _info("newest", 9)])
    asyncio.run(sb.pull())  # e.g. a download right after a deploy
    assert calls["connect"] == ["newest"] and calls["synced"] == ["pull", "push"] and calls["create"] == []
    assert sb._sbx.sandbox_id == "newest"


def test_a_reader_never_creates_a_sandbox(tmp_path, monkeypatch):
    sb, calls = _restartable(tmp_path, monkeypatch, [])
    asyncio.run(sb.pull())
    assert sb._sbx is None and calls["create"] == [] and calls["synced"] == []


def test_ensure_reattaches_before_creating_and_new_sandboxes_pause_instead_of_dying(tmp_path, monkeypatch):
    sb, calls = _restartable(tmp_path, monkeypatch, [_info("kept", 3)])
    asyncio.run(sb.ensure())
    assert sb._sbx.sandbox_id == "kept" and calls["create"] == []

    fresh, calls = _restartable(tmp_path, monkeypatch, [])
    with pytest.raises(RuntimeError, match="stop here"):
        asyncio.run(fresh.ensure())
    assert calls["create"][0]["lifecycle"] == {"on_timeout": "pause"}


def test_deleting_a_project_kills_its_paused_sandboxes(tmp_path, monkeypatch):
    sb, calls = _restartable(tmp_path, monkeypatch, [_info("a", 1), _info("b", 2)])
    asyncio.run(sb.forget())
    assert calls["kill"] == ["a", "b"] and sb._sbx is None
