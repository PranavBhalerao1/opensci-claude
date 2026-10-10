"""Task attempts must not see each other's output (offline, deterministic: no sleeps, no network).

Regression for a real run: T2.2 attempt 1 started a background job and failed; attempt 2 fixed
src/runner.py but never re-ran it; attempt 1's job then finished, wrote data/results_raw.parquet,
and the verifier accepted it as attempt 2's result. The invariant: output produced by an earlier
attempt is never accepted as a later attempt's output, even if the old process cannot be killed.

The E2B side of a real E2BSandbox is faked (FakeE2B): commands are interpreted, not run. A background
job writes its output only when the test calls finish(), so "the old job finishes after attempt 2
started" is an explicit step, not a timing accident.
"""

import asyncio
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from sqlmodel import Session

from app.db import Project, Run, TaskState, engine
from app.execution import orchestrator
from app.execution.agent import AgentResult
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.sandbox import ExecResult
from app.execution.tools import TOOLS, ToolContext

OUT = "data/results_raw.parquet"
AGENT_TOOLS = ["run_python", "run_shell", "write_file", "edit_file", "read_file", "start_process",
               "check_process", "stop_process"]


class FakeE2B:
    """Stands in for the E2B sandbox behind an E2BSandbox."""

    def __init__(self, sb: E2BSandbox):
        self.sb = sb
        self.jobs: dict[str, dict] = {}  # background jobs: name → {task, alive, writes}
        self.remote: dict[str, str] = {}  # remote writes not yet pulled to the host
        self.kill_fails = False
        self.pull_fails = False
        self.reaps: list[str | None] = []
        sb._sbx = self
        sb.ensure = self._noop
        sb._push = self._noop
        sb._pull = self._pull
        sb._sh = self._sh

    # the parts of e2b.AsyncSandbox that E2BSandbox touches directly
    async def set_timeout(self, seconds):
        pass

    async def is_running(self):
        return True

    async def kill(self):
        pass

    async def _noop(self):
        pass

    def _program(self, command: str) -> dict[str, str]:
        """`produce <path>` writes <path>, stamped with the src/runner.py it ran."""
        m = re.search(r"produce ([\w./-]+)", command)
        if not m:
            return {}
        code = self.sb.path("src/runner.py")
        return {m.group(1): "made by " + (code.read_text() if code.exists() else "no code")}

    async def _sh(self, cmd, timeout, cwd=None, envs=None, clip=True):
        task = (envs or {}).get("OPENSCI_TASK")
        if "setsid -f" in cmd:  # start_process: the job reads its code now, writes on finish()
            name = re.search(r"\.logs/([\w-]+)\.pid", cmd).group(1)
            self.jobs[name] = {"task": task, "alive": True, "writes": self._program(cmd)}
            return ExecResult(0, "4242\n", "")
        if "/proc" in cmd:  # the reaper
            want, mode = shlex.split(cmd)[-2:]
            tid = want.split("=", 1)[1]
            self.reaps.append(tid if mode == "exact" else None)
            hit = [j for j in self.jobs.values()
                   if j["alive"] and j["task"] is not None and (mode != "exact" or j["task"] == tid)]
            if not self.kill_fails:
                for j in hit:
                    j["alive"] = False
            return ExecResult(0, "alive 4242\n" if any(j["alive"] for j in hit) else "clean\n", "")
        if cmd.startswith("timeout"):  # run_python / run_shell in the foreground
            cell = re.search(r"/home/user/workspace/(\.scratch/\S+\.py)", cmd)
            self.remote.update(self._program(self.sb.path(cell.group(1)).read_text() if cell else cmd))
            return ExecResult(0, "ok\n", "")
        return ExecResult(0, "", "")  # stop / stop_all kill commands

    def finish(self, name: str) -> None:
        """The job completes now; a job that was killed writes nothing."""
        job = self.jobs[name]
        if job["alive"]:
            self.remote.update(job["writes"])
            self.remote[f".logs/{name}.exit"] = "0\n"
            job["alive"] = False

    async def _pull(self):
        if self.pull_fails:
            raise RuntimeError("Listing the E2B workspace failed")
        for rel, text in self.remote.items():
            p = self.sb.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.remote.clear()
        for name, state in self.sb.procs.items():
            if state == "running" and (self.sb.root / ".logs" / f"{name}.exit").exists():
                self.sb.procs[name] = "done"


# ── Harness ────────────────────────────────────────────────────────────────


def _task(tid: str = "T2.2", outputs: tuple[str, ...] = (OUT,), retries: int = 1) -> dict:
    return {"id": tid, "title": "Run the experiment", "agent": "A1", "objective": "o", "steps": ["s"],
            "inputs": [], "outputs": [{"path": p, "format": "parquet", "description": "d"} for p in outputs],
            "acceptance_checks": ["results exist"], "depends_on": [], "tools": AGENT_TOOLS, "resources": [],
            "compute": {"kind": "cpu", "est_minutes": 5, "timeout_minutes": 15}, "max_cost_usd": 0.5,
            "retries": retries, "human_required": False}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A project with one task, a faked E2B sandbox, scripted agents and an existence-only verifier."""
    sb = E2BSandbox("_attempts")
    sb.root = tmp_path
    fake = FakeE2B(sb)
    monkeypatch.setattr(orchestrator, "sandbox_for", lambda pid: sb)

    class Env:
        pass

    e = Env()
    e.sb, e.fake, e.prompts, e.scripts, e.verdicts, e.specs = sb, fake, [], [], [], []
    e.task = _task()
    e.mp = {"title": "t", "summary": "s", "datasets": [], "tasks": [e.task], "agents": [
        {"id": "A1", "name": "Runner", "model_tier": "standard", "tools": AGENT_TOOLS, "instructions": "i"}]}
    with Session(engine) as s:
        p = Project(title="_attempts_test")
        s.add(p)
        s.commit()
        s.refresh(p)
        r = Run(project_id=p.id, kind="blueprint", status="done", result={"master_plan": e.mp})
        s.add(r)
        s.commit()
        s.refresh(r)
        st = TaskState(project_id=p.id, blueprint_run_id=r.id, task_id="T2.2", agent="A1")
        s.add(st)
        s.commit()
        e.pid, e.sid, rid = p.id, st.id, r.id

    async def run_agent(spec, prompt, ctx, on_event=None):
        e.prompts.append(prompt)
        e.specs.append(spec)
        return await e.scripts.pop(0)(ctx)

    async def verify(task, sandbox, policy, report=None, amendments=None, *rest, **kw):
        # Passes whenever it is asked: the real verifier accepted the binary parquet on sight.
        ok = e.verdicts.pop(0) if e.verdicts else True
        return [{"check": c, "passed": ok, "reason": "seen"} for c in task["acceptance_checks"]]

    monkeypatch.setattr(orchestrator, "run_agent", run_agent)
    monkeypatch.setattr(orchestrator, "_verify", verify)

    async def attempt():
        await orchestrator._execute(e.pid, e.mp, e.task, e.sid, "default", None)

    def state() -> TaskState:
        with Session(engine) as s:
            return s.get(TaskState, e.sid)

    e.attempt, e.state = attempt, state
    yield e
    with Session(engine) as s:
        s.delete(s.get(TaskState, e.sid))
        s.delete(s.get(Run, rid))
        s.delete(s.get(Project, e.pid))
        s.commit()


async def tool(ctx: ToolContext, tool_name: str, **args) -> str:
    return await TOOLS[tool_name].handler(ctx, args)


async def _attempt1_starts_job_and_fails(ctx):
    await tool(ctx, "write_file", path="src/runner.py", content="buggy v1\n")
    out = await tool(ctx, "start_process", name="run", command=f"python src/runner.py  # produce {OUT}")
    assert out.startswith("Started run")
    return AgentResult("step_limit", "Stopped after 80 steps.")


# ── The T2.2 race ──────────────────────────────────────────────────────────


def test_stale_job_from_failed_attempt_is_never_accepted(env):
    """Attempt 1's job finishes after attempt 2 started and changed the code: its output must not pass."""

    async def attempt2(ctx):
        await tool(ctx, "edit_file", path="src/runner.py", old="buggy v1", new="fixed v2, seeds pinned")
        env.fake.finish("run")  # attempt 1's job completes now, mid-attempt 2
        await tool(ctx, "run_shell", command="ls data")  # any command syncs the workspace
        return AgentResult("budget_exceeded", "Stopped at the budget.")  # never re-ran the experiment

    async def scenario():
        env.scripts[:] = [_attempt1_starts_job_and_fails, attempt2]
        await env.attempt()
        assert env.state().status == "pending" and env.state().attempts == 1  # retry scheduled
        await env.attempt()

    asyncio.run(scenario())
    st = env.state()
    out = env.sb.path(OUT)
    assert st.status != "done", f"stale output accepted: {out.read_text() if out.exists() else '-'}"
    assert not (out.exists() and "buggy v1" in out.read_text())  # the old job never published
    assert st.status == "failed" and any(OUT in i for i in st.issues)
    assert not env.fake.jobs["run"]["alive"] and env.sb.procs["run"] == "stopped"


def test_output_left_by_failed_attempt_must_be_regenerated(env):
    """No race: attempt 1 wrote the output and failed another check; attempt 2 changed the code
    but did not re-run it. The leftover output is not attempt 2's and must not pass."""

    async def attempt1(ctx):
        await tool(ctx, "write_file", path="src/runner.py", content="buggy v1\n")
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def attempt2(ctx):
        await tool(ctx, "edit_file", path="src/runner.py", old="buggy v1", new="fixed v2, seeds pinned")
        return AgentResult("success", "fixed the bug")

    async def scenario():
        env.scripts[:] = [attempt1, attempt2]
        env.verdicts[:] = [False]  # attempt 1 fails an acceptance check
        await env.attempt()
        assert env.state().status == "pending"
        await env.attempt()

    asyncio.run(scenario())
    st = env.state()
    assert "buggy v1" in env.sb.path(OUT).read_text()
    assert st.status == "failed"
    assert any("Not written by this attempt" in i and OUT in i for i in st.issues), st.issues
    assert "LEFT OVER FROM AN EARLIER ATTEMPT" not in env.prompts[0]  # fresh attempts are unchanged
    assert "LEFT OVER FROM AN EARLIER ATTEMPT" in env.prompts[1] and OUT in env.prompts[1]


def test_current_attempt_output_is_accepted(env):
    async def attempt2(ctx):
        await tool(ctx, "edit_file", path="src/runner.py", old="buggy v1", new="fixed v2, seeds pinned")
        env.fake.finish("run")  # the old job, already reaped, writes nothing
        await tool(ctx, "start_process", name="run2", command=f"python src/runner.py  # produce {OUT}")
        env.fake.finish("run2")
        status = await tool(ctx, "check_process", name="run2")
        assert "exited with code 0" in status, status
        return AgentResult("success", "re-ran with the fix")

    async def scenario():
        env.scripts[:] = [_attempt1_starts_job_and_fails, attempt2]
        await env.attempt()
        await env.attempt()

    asyncio.run(scenario())
    assert env.state().status == "done", env.state().issues
    assert env.sb.path(OUT).read_text() == "made by fixed v2, seeds pinned\n"
    assert env.fake.jobs["run"]["task"] == "T2.2" and env.fake.jobs["run2"]["task"] == "T2.2"  # tagged


def test_single_attempt_task_still_works_and_its_processes_end_with_it(env):
    async def attempt1(ctx):
        await tool(ctx, "write_file", path="src/runner.py", content="v1\n")
        await tool(ctx, "run_python", code=f"# produce {OUT}")
        await tool(ctx, "start_process", name="server", command="python -m http.server")  # left running
        return AgentResult("success", "done")

    async def scenario():
        env.scripts[:] = [attempt1]
        await env.attempt()
        assert env.fake.reaps[-1] == "T2.2"
        assert "stopped" in await tool(ToolContext(env.pid, env.sb, None), "check_process", name="server")

    asyncio.run(scenario())
    assert env.state().status == "done" and env.state().attempts == 1
    assert env.sb.path(OUT).read_text() == "made by v1\n"
    assert not env.fake.jobs["server"]["alive"] and env.sb.procs["server"] == "stopped"


def test_failed_kill_cannot_let_old_output_through(env):
    """If the old job cannot be stopped, nothing written from then on can be attributed to the
    new attempt: it does not run, keeps its attempt count and the earlier feedback."""
    env.fake.kill_fails = True

    async def after_resume(ctx):
        await tool(ctx, "edit_file", path="src/runner.py", old="buggy v1", new="fixed v2, seeds pinned")
        return AgentResult("budget_exceeded", "Stopped at the budget.")  # never re-ran the experiment

    async def scenario():
        env.scripts[:] = [_attempt1_starts_job_and_fails, after_resume]
        await env.attempt()
        assert env.state().status == "pending"
        await env.attempt()  # the job survives the kill: this attempt must not run at all
        st = env.state()
        assert st.status == "failed" and st.attempts == 1 and len(env.scripts) == 1  # no retry used up
        assert "could not be confirmed stopped" in st.note and "Missing outputs" in st.note  # feedback kept
        env.fake.finish("run")  # the unkillable job publishes late
        await env.sb.pull()
        assert "buggy v1" in env.sb.path(OUT).read_text()
        _update_status(env.sid, "pending")  # the user resumes (prepare_states)
        await env.attempt()  # the job is gone now: the fence is clean, its late output is a leftover

    asyncio.run(scenario())
    st = env.state()
    assert st.status == "failed", "late output of an unkillable job was accepted"
    assert any("Not written by this attempt" in i for i in st.issues), st.issues
    assert OUT in env.prompts[-1] and "LEFT OVER FROM AN EARLIER ATTEMPT" in env.prompts[-1]


def _update_status(state_id: str, status: str) -> None:
    with Session(engine) as s:
        st = s.get(TaskState, state_id)
        st.status = status
        s.add(st)
        s.commit()


def test_fence_fails_closed_when_the_workspace_cannot_be_synced(env):
    env.fake.pull_fails = True
    fence = asyncio.run(env.sb.fence("T2.2", [OUT]))
    assert not fence.clean


def test_retry_runs_again_after_a_failed_attempt(env):
    async def attempt2(ctx):
        await tool(ctx, "run_shell", command=f"python src/runner.py  # produce {OUT}")
        return AgentResult("success", "done")

    async def scenario():
        env.scripts[:] = [_attempt1_starts_job_and_fails, attempt2]
        await env.attempt()
        assert (env.state().status, env.state().attempts) == ("pending", 1)
        await env.attempt()

    asyncio.run(scenario())
    assert (env.state().status, env.state().attempts) == ("done", 2)
    assert "PREVIOUS ATTEMPT FAILED" in env.prompts[1]


@pytest.mark.parametrize("tier,policy", [("standard", "default"), ("reasoning", "default"), ("bulk", "default"),
                                         ("standard", "minimal"), ("reasoning", "economy")])
def test_execution_effort_is_high_on_every_attempt(env, tier, policy):
    """Every execution-agent attempt runs at HIGH effort, whatever the tier or policy: the
    first attempt and each retry alike, with adaptive thinking and the usual output budget."""
    from app.llm import MAX_TOKENS, THINKING

    env.task["retries"] = 2
    env.mp["agents"][0]["model_tier"] = tier

    async def fail(ctx):
        return AgentResult("failed", "try again")

    async def scenario():
        env.scripts[:] = [fail, fail, fail]
        for _ in range(3):
            await orchestrator._execute(env.pid, env.mp, env.task, env.sid, policy, None)

    asyncio.run(scenario())
    assert [s.reasoning_effort for s in env.specs] == ["high", "high", "high"]
    assert env.state().status == "failed" and env.state().attempts == 3
    assert THINKING == {"type": "adaptive"} and MAX_TOKENS == 32_000


def test_spawned_subagents_run_at_high_effort(env, monkeypatch):
    """Sub-agents spawned by an execution agent inherit its HIGH effort, bulk tier included."""
    env.mp["agents"][0]["model_tier"] = "bulk"
    env.mp["agents"][0]["tools"] = AGENT_TOOLS + ["spawn_subagents"]
    env.task["tools"] = AGENT_TOOLS + ["spawn_subagents"]
    specs = []

    async def run_agent(spec, prompt, ctx, on_event=None):
        specs.append(spec)
        if "›" not in spec.name:  # the parent execution agent spawns two children
            await ctx.spawn([{"name": "a", "instructions": "x", "outputs": []},
                             {"name": "b", "instructions": "y", "outputs": []}])
        return AgentResult("failed", "try again")

    monkeypatch.setattr(orchestrator, "run_agent", run_agent)
    asyncio.run(orchestrator._execute(env.pid, env.mp, env.task, env.sid, "minimal", None))
    assert len(specs) == 3 and sum("›" in s.name for s in specs) == 2
    assert [s.reasoning_effort for s in specs] == ["high", "high", "high"]


def test_reaping_one_task_leaves_other_tasks_alone(env):
    async def scenario():
        a = ToolContext(env.pid, env.sb, None, owner="TA")
        b = ToolContext(env.pid, env.sb, None, owner="TB")
        await tool(a, "start_process", name="a", command="sleep 1000")
        await tool(b, "start_process", name="b", command=f"sleep 1000  # produce {OUT}")
        fence = await env.sb.fence("TA", [])
        assert fence.clean
        assert not env.fake.jobs["a"]["alive"] and env.fake.jobs["b"]["alive"]
        assert env.sb.procs == {"a": "stopped", "b": "running"}
        env.fake.finish("b")
        assert "exited with code 0" in await tool(b, "check_process", name="b")
        assert env.sb.path(OUT).read_text().startswith("made by")
        assert await env.sb.reap(None)  # stop_all's sweep: every task's processes

    asyncio.run(scenario())


def test_parallel_contexts_never_share_a_cell_file(env):
    seen = []

    async def run(argv, timeout, owner=None):
        seen.append((argv[-1], Path(argv[-1]).read_text(), owner))
        return ExecResult(0, "", "")

    env.sb.run = run
    a = ToolContext(env.pid, env.sb, None, owner="TA")
    b = ToolContext(env.pid, env.sb, None, owner="TB")

    async def scenario():
        await asyncio.gather(tool(a, "run_python", code="print('a')"), tool(b, "run_python", code="print('b')"))

    asyncio.run(scenario())
    assert len({path for path, _, _ in seen}) == 2
    assert sorted((code, owner) for _, code, owner in seen) == [("print('a')", "TA"), ("print('b')", "TB")]


# ── Sandbox pieces ─────────────────────────────────────────────────────────


def test_owner_tag_reaches_every_command(tmp_path):
    sb = E2BSandbox("_t")
    assert sb._env("T2.2")["OPENSCI_TASK"] == "T2.2"
    assert "OPENSCI_TASK" not in sb._env()


def test_stale_detects_files_this_attempt_did_not_write(tmp_path):
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    for rel in ("a.csv", "keep.csv", "runs/s0.json", "runs/s1.json", "gone.csv"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("old")
    paths = ["a.csv", "keep.csv", "runs", "gone.csv", "new.csv"]
    fence = asyncio.run(sb.fence("T", paths))  # no E2B sandbox in this process: trivially clean
    assert fence.clean and fence.leftovers() == ["a.csv", "keep.csv", "runs", "gone.csv"]
    (tmp_path / "a.csv").write_text("regenerated")
    (tmp_path / "runs/s1.json").write_text("regenerated")
    (tmp_path / "gone.csv").unlink()
    (tmp_path / "new.csv").write_text("new")
    assert sb.stale(fence, paths) == {"keep.csv": ["keep.csv"], "runs": ["runs/s0.json"]}


def test_stopped_process_name_can_be_reused(env):
    async def scenario():
        ctx = ToolContext(env.pid, env.sb, None, owner="T2.2")
        await tool(ctx, "start_process", name="run", command="sleep 1000")
        with pytest.raises(ValueError, match="already running"):
            await tool(ctx, "start_process", name="run", command="sleep 1")
        assert await env.sb.reap("T2.2")
        assert "stopped" in await tool(ctx, "check_process", name="run")
        assert (await tool(ctx, "start_process", name="run", command="sleep 1")).startswith("Started run")

    asyncio.run(scenario())


def test_subagents_cannot_outlive_their_attempt(env, monkeypatch):
    """One sub-agent crashing must not leave its siblings running unawaited."""
    finished = []

    async def run_agent(spec, prompt, ctx, on_event=None):
        if "crash" in prompt:
            raise RuntimeError("model API error")
        await asyncio.sleep(0)  # yields, so the crash happens while this one is still running
        finished.append(ctx.owner)
        return AgentResult("success", "ok")

    monkeypatch.setattr(orchestrator, "run_agent", run_agent)
    from app.execution.agent import AgentSpec

    spec = AgentSpec(name="Runner", instructions="i", model="m", tools=["spawn_subagents"])
    ctx = ToolContext(env.pid, env.sb, None, owner="T2.2")
    spawn = orchestrator._subagent_runner(spec, ctx, env.sid, [0.0])
    out = asyncio.run(spawn([{"name": "a", "instructions": "crash", "outputs": []},
                             {"name": "b", "instructions": "work", "outputs": []}]))
    assert finished == ["T2.2"]  # the sibling ran to completion, tagged with the attempt's task
    assert out[0]["status"] == "error" and "model API error" in out[0]["summary"]
    assert out[1]["status"] == "success"


@pytest.mark.skipif(not Path("/proc/self/environ").exists() or not hasattr(os, "setsid"),
                    reason="needs Linux /proc (runs remotely in E2B)")
def test_reaper_script_kills_tagged_trees_only():
    from app.execution.e2b_sandbox import _REAP

    tagged = subprocess.Popen(["setsid", "sh", "-c", "env -i sleep 300 & sleep 300"],
                              env={**os.environ, "OPENSCI_TASK": "Tx"})
    other = subprocess.Popen(["sleep", "300"], env={**os.environ, "OPENSCI_TASK": "Ty"})
    plain = subprocess.Popen(["sleep", "300"])
    try:
        out = subprocess.run([sys.executable, "-c", _REAP, "OPENSCI_TASK=Tx", "exact"],
                             capture_output=True, text=True, timeout=60).stdout
        assert out.strip() == "clean", out
        assert tagged.wait(10) is not None  # killed
        assert other.poll() is None and plain.poll() is None  # other task and untagged: untouched
        out = subprocess.run([sys.executable, "-c", _REAP, "OPENSCI_TASK=", "prefix"],
                             capture_output=True, text=True, timeout=60).stdout
        assert out.strip() == "clean" and other.wait(10) is not None and plain.poll() is None
    finally:
        for p in (tagged, other, plain):
            p.kill()
