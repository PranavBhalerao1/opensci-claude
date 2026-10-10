"""Stage 6 · Execution: run master_plan.json.

Schedules blueprint tasks in dependency order (parallel where possible), runs
each with its agent in the project sandbox, verifies outputs (existence in
code, acceptance checks by a cheap model), retries with feedback, and pauses at
the project budget or when the owner's credits run out (agents also check credits
before every step). Guided mode pauses at human checkpoints. State lives in the
TaskState table, so a restarted server resumes where it left off.
"""

import asyncio
import contextlib
import inspect
import json
import re
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .. import beta
from ..config import settings
from ..db import Project, Run, Secret, TaskState, Usage, engine
from ..jobs import RunHandle
from ..llm import TRANSIENT_ERRORS, parse
from . import catalog
from .agent import AgentSpec, run_agent
from .sandbox import SandboxUnreachable, sandbox_for
from .tools import TOOLS, ToolContext

# Network and provider failures, not the task's: they do not use up an attempt; the run waits.
INFRASTRUCTURE = (SandboxUnreachable, *TRANSIENT_ERRORS)
NETWORK_PAUSE = "network: "
NETWORK_RETRY = (30, 60, 120, 240, 480)  # seconds before each automatic resume; then wait for the user
MAX_PARALLEL = 4
MAX_AGENT_STEPS = 80
MAX_EVENTS = 150
PREVIEW_CHARS = 12_000  # whole document up to this size; longer ones show head and tail
TEXT_SUFFIXES = {".csv", ".tsv", ".json", ".md", ".txt", ".py", ".yaml", ".yml", ".tex", ".bib", ".r", ".qmd", ".log"}
SATISFIED = {"done", "skipped"}
TERMINAL = {"done", "skipped", "failed", "blocked", "cancelled"}

COMMON_INSTRUCTIONS = """\
You are {name}, an agent on an OpenScientist research team. Today's date is {today}.
Work only inside the project workspace (your current directory); other agents share it.
- Produce exactly the outputs listed, at exactly those paths.
- Check your work before reporting: print shapes, heads, summary statistics.
- Keep tool output short: print summaries, never whole large files.
- Record data provenance (source URLs, access dates, versions) in files you write.
- NEVER fabricate data, results or citations. If something is impossible (data
  unavailable, access denied, missing software), report status "failed" or
  "partial" and explain the issue.
- You are not limited to known tools or APIs. If you need a service, database,
  web server or software, find it yourself: web_search, read its documentation
  with read_webpage, then use it via http_request or by writing client code
  (submit jobs, poll for results, parse outputs). Install software with
  install_packages (pip) or install_conda_packages (conda-forge/bioconda), or
  download and build it in the workspace.
- For long computations (training, simulations, docking, servers) use
  start_process and poll with check_process/wait instead of blocking. When
  run_gpu_jobs is available, run GPU-heavy work (training, grids) there, in parallel.
- Before any experiment grid: run ONE full-length representative job on the target
  hardware, measure its real wall time, and size horizons/timeouts from that — never
  from a tiny calibration. Keep instrumentation light (log at checkpoints, not every
  step) so runs stay fast.
- Split large independent work (sweeps, per-sample or per-target runs) across
  spawn_subagents when available.
- Background research is already done: context/ holds the brief, the chosen gap and
  the literature notes (with closest prior work). Use it rather than re-surveying.
- Share useful discoveries with post_note; check read_notes for what others found.
- When a request fails (4xx/5xx), debug it: retry with minimal headers (no custom
  Accept/Content-Type unless the docs require them), compare with the
  http_request tool (a known-good client), read the error body, and check the docs.
- If a service truly requires an account or API key, call request_credential.
- Write real, tested code: run it, fix errors, and keep code in files (src/, scripts/).
- Finish by calling report_result with the artifacts you produced.

{role}"""


class CheckResult(BaseModel):
    check: str
    passed: bool
    reason: str = Field(description="One sentence citing what in the files supports the verdict")


class Verdict(BaseModel):
    results: list[CheckResult]


VERIFY_INSTRUCTIONS = """\
You verify a research task's outputs against its acceptance checks, using only the
evidence given. FACTS are computed by the platform (file statistics, test runs it
executed itself); trust them. The AGENT REPORT is the agent's own claim: accept it
only where it is consistent with the files and FACTS, never as sole proof of a
number. A check passes if the evidence shows it is met; if the evidence cannot
confirm it, fail it and say what is missing. Your verdict must agree with your reason."""


# ── Control ────────────────────────────────────────────────────────────────


class Control:
    """In-memory handle for pausing, resuming and cancelling a live execution."""

    def __init__(self) -> None:
        self.go = asyncio.Event()
        self.go.set()
        self.cancelled = False
        self.reason: str | None = None

    def pause(self, reason: str) -> None:
        self.reason = reason
        self.go.clear()

    def resume(self) -> None:
        self.reason = None
        self.go.set()


_controls: dict[str, Control] = {}


def control(project_id: str) -> Control | None:
    return _controls.get(project_id)


def model_for(tier: str, policy: str) -> str:
    """Map an agent's tier to a model under the project's model policy."""
    tiers = {"reasoning": settings.model_reasoning, "standard": settings.model_standard, "bulk": settings.model_bulk}
    if policy == "minimal":
        return settings.model_bulk
    if policy == "economy" and tier == "reasoning":
        return settings.model_standard
    return tiers.get(tier, settings.model_standard)


ESCALATE = {"bulk": "standard", "standard": "reasoning", "reasoning": "reasoning"}
EFFORT_LEVELS = ("low", "medium", "high")


def escalated_effort(base: str, attempt: int) -> str:
    """First attempt: the stage's base effort. Each attempt after a failure raises effort one
    level (low -> medium -> high), capped at high: since every model tier now resolves to the
    same Sonnet 4.6 model, effort is the only lever a retry has left to actually try harder."""
    idx = EFFORT_LEVELS.index(base) if base in EFFORT_LEVELS else 1
    return EFFORT_LEVELS[min(idx + max(0, attempt - 1), len(EFFORT_LEVELS) - 1)]


def escalated_model(tier: str, policy: str, attempt: int) -> tuple[str, bool]:
    """First attempt: the assigned tier under the policy. Retries escalate one tier
    (cheap first, stronger only when a task has already failed). Minimal policy
    escalates at most to the standard tier."""
    base = model_for(tier, policy)
    if attempt <= 1:
        return base, False
    up = ESCALATE[tier]
    if policy == "minimal":
        up = "standard"
    stronger = model_for(up, "default" if policy == "minimal" else policy)
    return stronger, stronger != base


def current_budget(project_id: str) -> float:
    """Read the budget fresh each time, so raising it during a live run takes effect."""
    with Session(engine) as s:
        cfg = s.get(Project, project_id).settings or {}
    return float((cfg.get("budget") or {}).get("llm_usd", 15.0))


def spent(project_id: str) -> float:
    """LLM spend across every execution run of the project."""
    with Session(engine) as s:
        run_ids = s.exec(select(Run.id).where(Run.project_id == project_id, Run.kind == "execute")).all()
        if not run_ids:
            return 0.0
        return float(s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.run_id.in_(run_ids))).one())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update(state_id: str, **fields) -> None:
    with Session(engine) as s:
        st = s.get(TaskState, state_id)
        for k, v in fields.items():
            setattr(st, k, v)
        s.add(st)
        s.commit()


def _append_event(state_id: str, event: dict) -> None:
    with Session(engine) as s:
        st = s.get(TaskState, state_id)
        st.events = [*st.events, {**event, "t": _now().isoformat()}][-MAX_EVENTS:]
        s.add(st)
        s.commit()


# ── Task execution ─────────────────────────────────────────────────────────


def _task_prompt(mp: dict, task: dict, states: dict[str, TaskState], feedback: str | None,
                 amendments: str = "") -> str:
    datasets = {d["id"]: d for d in mp["datasets"]}
    used = [datasets[r] for r in task["resources"] if r in datasets]
    used += [datasets[i["source"].split(":", 1)[1]] for i in task["inputs"]
             if i["source"].startswith("dataset:") and i["source"].split(":", 1)[1] in datasets]
    resources = [r for name in task["resources"] for r in catalog.search(name, 1)]
    upstream = [
        f"- {d}: {states[d].summary or '(no summary)'} Artifacts: {', '.join(states[d].artifacts) or 'none'}"
        for d in task["depends_on"] if d in states
    ]
    parts = [
        f"STUDY: {mp['title']}\n{mp['summary']}",
        f"YOUR TASK {task['id']}: {task['title']}\nObjective: {task['objective']}",
        "Steps:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(task["steps"])),
        "Inputs:\n" + ("\n".join(f"- {i['path']} (from {i['source']})" for i in task["inputs"]) or "- none"),
        "Required outputs:\n" + "\n".join(f"- {o['path']} [{o['format']}]: {o['description']}" for o in task["outputs"]),
        "Acceptance checks (a verifier will test these):\n" + "\n".join(f"- {c}" for c in task["acceptance_checks"]),
    ]
    if upstream:
        parts.append("Upstream results:\n" + "\n".join(upstream))
    if used:
        parts.append("Datasets:\n" + json.dumps(list({d["id"]: d for d in used}.values()), ensure_ascii=False))
    if resources:
        parts.append("Resource notes:\n" + json.dumps(resources, ensure_ascii=False))
    if amendments:
        parts.insert(1, "REVIEWER-APPROVED AMENDMENTS (they override the blueprint, including your steps and "
                        "acceptance checks, wherever they conflict; also in context/AMENDMENTS.md):\n" + amendments)
    if feedback:
        parts.append(
            f"PREVIOUS ATTEMPT FAILED. Fix this:\n{feedback}\n\nFiles written by the failed attempt may be "
            "stale or wrong. Before reporting, make sure every file you touched (including status, log and "
            "provenance files) reflects the final result; delete ones that no longer apply."
        )
    return "\n\n".join(parts)


def _previews(sandbox, outputs: list[dict]) -> str:
    blocks = []
    for o in outputs:
        try:
            p = sandbox.path(o["path"])
        except ValueError:
            continue
        if not p.exists():
            blocks.append(f"### {o['path']}\nMISSING")
            continue
        if p.is_dir():
            files = sorted(x.name for x in p.iterdir())[:40]
            blocks.append(f"### {o['path']} (directory)\n" + "\n".join(files))
            continue
        size = p.stat().st_size
        if p.suffix.lower() in (".csv", ".tsv") and size:
            rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
            head, body = rows[0], rows[1:]
            sample = body[:12] + (["…"] + body[-5:] if len(body) > 17 else body[12:])
            blocks.append(
                f"### {o['path']} ({size:,} bytes)\nFACTS: {len(body):,} data rows (excluding the header); "
                f"columns: {head}\nFirst and last rows:\n{head}\n" + "\n".join(sample)
            )
        elif p.suffix.lower() in TEXT_SUFFIXES and size:
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n")
            if len(text) > PREVIEW_CHARS:
                head, tail = PREVIEW_CHARS * 2 // 3, PREVIEW_CHARS // 3
                text = f"{text[:head]}\n… [{len(text) - PREVIEW_CHARS:,} chars omitted] …\n{text[-tail:]}"
            blocks.append(f"### {o['path']} ({size:,} bytes, {lines:,} lines)\n{text}")
        else:
            blocks.append(f"### {o['path']} ({size:,} bytes, binary {p.suffix or 'file'}; content not shown)")
    return "\n\n".join(blocks)


# A workspace path in an acceptance check: at least one directory part, optionally a glob or brace pattern.
_NAMED_PATH = re.compile(r"(?<![\w/.-])(?:\./)?(?:[\w.-]+/)+[\w.*?{},\[\]-]*")
MAX_NAMED_PATHS = 20


def _named_paths(sandbox, task: dict) -> list[str]:
    """Workspace paths the acceptance checks name that are not declared outputs (a setup task's
    directories, a log, an upstream file). The previews cover only declared outputs, so without
    these the verifier has no platform evidence for such a check, only the agent's claim."""
    outputs = {o["path"].strip().removeprefix("./").rstrip("/") for o in task["outputs"]}
    found: list[str] = []
    for check in task["acceptance_checks"]:
        for m in _NAMED_PATH.finditer(check):
            token = m.group(0).removeprefix("./").rstrip(",.")
            if cut := [token.index(c) for c in "*?{[" if c in token]:  # a pattern: list its fixed directory
                token = token[:min(cut)]
                token = token[:token.rfind("/") + 1]
            rel = token.rstrip("/")
            if not rel or rel in outputs or rel in found:
                continue
            # A path, not a phrase like "train/test" or "T-shirt/top": it exists at the top level, is
            # written as a directory, or ends in a file extension.
            if (sandbox.root / rel.split("/")[0]).exists() or token.endswith("/") or \
                    re.search(r"\.[A-Za-z]\w{0,7}$", rel):
                found.append(rel)
    return found[:MAX_NAMED_PATHS]


def _path_facts(sandbox, rels: list[str]) -> str:
    lines = []
    for rel in rels:
        try:
            p = sandbox.path(rel)
        except ValueError:
            continue
        if p.is_dir():
            entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
            listing = (f"; entries: {', '.join(entries[:20])}" + (" …" if len(entries) > 20 else "")) if entries \
                else " (empty)"
            lines.append(f"- {rel}/: directory, {len(sandbox.files(rel))} file(s) inside{listing}")
        elif p.is_file():
            lines.append(f"- {rel}: file, {p.stat().st_size:,} bytes")
        else:
            lines.append(f"- {rel}: does not exist in the workspace")
    return ("FACTS: other workspace paths named in the acceptance checks (platform listing of the synced "
            "workspace; unlike declared outputs, these are not checked for files left by earlier attempts):\n"
            + "\n".join(lines)) if lines else ""


async def _run_tests(sandbox, outputs: list[dict]) -> str | None:
    """If the task produced tests, run them ourselves so 'tests pass' is a fact, not a claim."""
    tests = [o["path"] for o in outputs
             if o["path"].endswith(".py") and ("tests/" in o["path"] or o["path"].rsplit("/", 1)[-1].startswith("test_"))]
    tests = [t for t in tests if sandbox.path(t).is_file()]
    if not tests:
        return None
    await sandbox.install(["pytest"])
    res = await sandbox.run([str(sandbox.python), "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], 900)
    tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-15:])
    return f"FACTS: platform ran `pytest -q {' '.join(tests)}` → exit code {res.exit_code}\n{tail}"


async def _verify(task: dict, sandbox, policy: str, report: dict | None = None,
                  amendments: str | None = None, leftovers: dict[str, list[str]] | None = None) -> list[dict]:
    if not task["acceptance_checks"]:
        return []
    evidence = "Output previews:\n" + _previews(sandbox, task["outputs"])
    if facts := _path_facts(sandbox, _named_paths(sandbox, task)):
        evidence += "\n\n" + facts
    if leftovers:
        evidence += ("\n\nFACTS: these files in output directories were left by an earlier attempt and NOT written "
                     "by the attempt being verified:\n"
                     + "\n".join(f"- {d}: {', '.join(files[:30])}" + (" …" if len(files) > 30 else "")
                                 for d, files in leftovers.items()))
    if amendments:
        evidence = ("REVIEWER-APPROVED AMENDMENTS (authoritative: where an acceptance check conflicts with them, "
                    "judge the check as amended and say so):\n" + amendments + "\n\n" + evidence)
    if tests := await _run_tests(sandbox, task["outputs"]):
        evidence = tests + "\n\n" + evidence
    if report:
        evidence += "\n\nAGENT REPORT (claims):\n" + json.dumps(report, ensure_ascii=False)[:4000]
    verdict = await parse(
        model=model_for("standard", policy),
        instructions=VERIFY_INSTRUCTIONS,
        messages=[{"role": "user", "content": "Acceptance checks:\n" + "\n".join(f"- {c}" for c in task["acceptance_checks"])
                   + "\n\n" + evidence}],
        schema=Verdict,
        # High: this is the acceptance-check gate between every task attempt and "done" —
        # a core scientific-integrity check, not a routine administrative one.
        reasoning_effort="high",
    )
    return [r.model_dump() for r in verdict.results]


def _task_tools(task: dict, agent: dict, sandbox) -> list[str]:
    tools = [t for t in task["tools"] if t in agent["tools"] and t in TOOLS] or list(agent["tools"])
    # GPU work goes to cloud GPUs when they are available, even if the blueprint predates them.
    if task["compute"]["kind"] in ("cuda_gpu", "apple_gpu") and "cuda_gpu" in sandbox.capabilities:
        tools += [t for t in ("run_gpu_jobs",) if t not in tools]
    return tools


def _subagent_runner(spec: AgentSpec, ctx: ToolContext, state_id: str, cost_box: list[float]):
    """Build the spawn callback: children share the workspace and cannot spawn further."""

    async def spawn(subtasks: list[dict]) -> list[dict]:
        child_tools = [t for t in spec.tools if t != "spawn_subagents"]

        async def one(sub: dict) -> dict:
            name = re.sub(r"[^A-Za-z0-9_-]", "_", sub["name"])[:30]
            child = AgentSpec(
                name=f"{spec.name} › {name}", instructions=spec.instructions, model=spec.model, tools=child_tools,
                max_steps=MAX_AGENT_STEPS, reasoning_effort=spec.reasoning_effort,
            )
            child_ctx = ToolContext(ctx.project_id, ctx.sandbox, ctx.http, agent_name=child.name, owner=ctx.owner,
                                    live=ctx.live)
            task = sub["instructions"] + "\n\nRequired outputs:\n" + "\n".join(f"- {o}" for o in sub["outputs"])
            res = await run_agent(child, task, child_ctx,
                                  on_event=lambda e: _append_event(state_id, {**e, "sub": name}))
            cost_box[0] += res.cost
            await ctx.sandbox.pull()
            missing = [o for o in sub["outputs"] if not ctx.sandbox.path(o).exists()]
            return {"name": name, "status": res.status, "summary": res.summary, "artifacts": res.artifacts,
                    "metrics": res.metrics, "missing_outputs": missing, "cost": round(res.cost, 4)}

        _append_event(state_id, {"type": "message", "step": 0, "text": f"Spawning {len(subtasks)} sub-agents",
                                 "cost": 0.0})
        # Wait for every sub-agent, even if one fails: none may keep working after its attempt ends.
        results = await asyncio.gather(*(one(s) for s in subtasks), return_exceptions=True)
        return [r if not isinstance(r, BaseException) else
                {"name": s["name"], "status": "error", "summary": f"{type(r).__name__}: {r}"}
                for s, r in zip(subtasks, results)]

    return spawn


def _requeue_on_credit_limit(state_id: str, me: TaskState, step: int, cost: float) -> None:
    """Credits ran out: not a failure. Re-queue without using up a retry (the note keeps any
    earlier feedback); the scheduler pauses on the credit limit and resume re-runs the task."""
    _append_event(state_id, {"type": "message", "step": step, "text": "Stopped: beta usage limit reached",
                             "cost": cost})
    _update(state_id, status="pending", attempts=me.attempts, cost=me.cost + cost, finished_at=_now())


def _requeue_on_infrastructure(state_id: str, me: TaskState, exc: Exception, cost: float) -> None:
    """A network or provider failure: not the task's. Re-queue it as it was before this attempt
    (attempt count, feedback), so no retry is used up; the scheduler waits for the connection."""
    _append_event(state_id, {"type": "message", "step": 0, "cost": cost,
                             "text": f"Interrupted by a network or service failure (not counted as an attempt): "
                                     f"{type(exc).__name__}: {exc}"[:600]})
    _update(state_id, status="pending", attempts=me.attempts, cost=me.cost + cost, finished_at=_now())


async def _execute(project_id: str, mp: dict, task: dict, state_id: str, policy: str, http: httpx.AsyncClient) -> None:
    with Session(engine) as s:
        states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == s.get(TaskState, state_id).blueprint_run_id))}
    me = next(st for st in states.values() if st.id == state_id)
    feedback = me.note if me.attempts else None
    amendments = project_amendments(project_id)
    if me.feedback:
        feedback = f"REVIEWER-APPROVED CHANGE (overrides earlier protocol where they conflict):\n{me.feedback}"
    sandbox = sandbox_for(project_id)
    outputs = [o["path"] for o in task["outputs"]]
    # Attempt boundary: stop whatever earlier attempts of this task left running, then record its
    # outputs. Only output files this attempt writes from here on can be accepted as its result.
    try:
        fence = await sandbox.fence(task["id"], outputs)
    except SandboxUnreachable as exc:  # nothing can be confirmed stopped, so nothing runs
        _requeue_on_infrastructure(state_id, me, exc, 0.0)
        raise
    if not fence.clean:
        # Fail closed: anything written from now on could be theirs. Not run, so no retry is used up.
        problem = ("Processes started by an earlier attempt of this task could not be confirmed stopped, so "
                   "outputs written now could not be told apart from theirs. Not run; resume to try again.")
        _append_event(state_id, {"type": "message", "step": 0, "text": problem, "cost": 0.0})
        _update(state_id, status="failed", issues=[problem], note=problem + (f"\n{me.note}" if me.note else ""),
                finished_at=_now())
        return
    # Keep the amendment on the task (the verifier needs it); it is replaced by the next review.
    _update(state_id, status="running", attempts=me.attempts + 1, started_at=_now(), finished_at=None)

    agent = next(a for a in mp["agents"] if a["id"] == task["agent"])
    model, escalated = escalated_model(agent["model_tier"], policy, me.attempts + 1)
    if escalated:
        _append_event(state_id, {"type": "message", "step": 0, "text": f"Retrying with a stronger model ({model})",
                                 "cost": 0.0})
    base_effort = "low" if agent["model_tier"] == "bulk" or policy == "minimal" else "medium"
    spec = AgentSpec(
        name=f"{agent['name']} ({task['id']})",
        instructions=COMMON_INSTRUCTIONS.format(
            name=agent["name"], role=agent["instructions"], today=_now().date().isoformat()
        ),
        model=model,
        tools=_task_tools(task, agent, sandbox),
        max_steps=MAX_AGENT_STEPS,
        reasoning_effort=escalated_effort(base_effort, me.attempts + 1),
    )
    ended: list[bool] = []
    ctx = ToolContext(project_id, sandbox, http, agent_name=agent["name"], owner=task["id"], live=lambda: not ended)
    sub_cost = [0.0]
    if "spawn_subagents" in spec.tools:
        ctx.spawn = _subagent_runner(spec, ctx, state_id, sub_cost)
    prompt = _task_prompt(mp, task, states, feedback, amendments)
    if leftover := fence.leftovers():
        prompt += ("\n\nLEFT OVER FROM AN EARLIER ATTEMPT: " + ", ".join(leftover) + ". These required outputs are "
                   "not accepted unless this attempt writes them again: regenerate them by re-running the code that "
                   "produces them. Copying or touching an old file is not regeneration.")
    try:
        res = await run_agent(spec, prompt, ctx, on_event=lambda e: _append_event(state_id, e))
    except INFRASTRUCTURE as exc:
        _requeue_on_infrastructure(state_id, me, exc, sub_cost[0])
        raise
    finally:
        # No process outlives the attempt that started it, whatever the outcome (this also brings
        # back what they wrote before they stopped). The next attempt's fence re-checks.
        ended.append(True)
        with contextlib.suppress(SandboxUnreachable):  # unreachable now: the next fence fails closed
            await sandbox.reap(task["id"])

    if res.status == "needs_credential":
        c = res.credential
        _update(
            state_id, status="human", attempts=me.attempts, cost=me.cost + res.cost + sub_cost[0],
            note=f"Needs credential {c['env_var']} for {c['service']}: {c['reason']}"
                 + (f" Sign up: {c['signup_url']}" if c.get("signup_url") else ""),
            finished_at=_now(),
        )
        return
    if res.status == "credit_limit":
        _requeue_on_credit_limit(state_id, me, res.steps, res.cost + sub_cost[0])
        return

    await sandbox.pull()  # checks and the verifier read the host copy of the workspace
    missing = [o["path"] for o in task["outputs"] if not sandbox.path(o["path"]).exists()]
    # Provenance: an output file left unchanged since the fence (a directory with nothing written in
    # it) was produced by an earlier attempt, not this one, and cannot pass as its result.
    left = sandbox.stale(fence, [p for p in outputs if p not in missing])
    stale = [p for p, files in left.items() if len(files) == len(sandbox.files(p))]
    leftovers = {p: files for p, files in left.items() if p not in stale}
    report = {"status": res.status, "summary": res.summary, "metrics": res.metrics, "issues": res.issues}
    # Verify whenever every output exists — an agent cut off by its step limit
    # may already have finished the work. An explicit "failed" report is trusted.
    verifiable = not missing and not stale and res.status != "failed"
    try:
        checks = await _verify(task, sandbox, policy, report, amendments, leftovers) if verifiable else []
    except beta.BetaLimitReached:  # the verifier's model call was refused for lack of credit
        _requeue_on_credit_limit(state_id, me, res.steps, res.cost + sub_cost[0])
        return
    except INFRASTRUCTURE as exc:
        _requeue_on_infrastructure(state_id, me, exc, res.cost + sub_cost[0])
        raise
    passed = verifiable and bool(checks or not task["acceptance_checks"]) and all(c["passed"] for c in checks)
    if passed and res.status == "step_limit":
        res.issues.append(f"Agent stopped ({res.status}) before reporting; outputs verified by the platform.")
    problems = (
        [f"Missing outputs: {', '.join(missing)}"] if missing else []
    ) + (
        [f"Not written by this attempt (left over from an earlier attempt): {', '.join(stale)}"] if stale else []
    ) + [f"Check failed: {c['check']} — {c['reason']}" for c in checks if not c["passed"]] + res.issues
    if not passed and res.status not in ("success", "partial"):
        problems.insert(0, f"Agent ended with status {res.status}: {res.summary}")

    retry = not passed and me.attempts + 1 <= int(task.get("retries", 1))
    _update(
        state_id,
        status="done" if passed else ("pending" if retry else "failed"),
        cost=me.cost + res.cost + sub_cost[0],
        summary=res.summary,
        artifacts=res.artifacts,
        checks=checks,
        issues=problems,
        note="\n".join(problems) if not passed else None,
        finished_at=_now(),
    )


# ── Scheduler ──────────────────────────────────────────────────────────────


def _write_context(project_id: str, sandbox) -> None:
    """Give agents the planning context (brief, gap, plan, literature notes) as files."""
    from ..agents.plan import build_context  # local import: plan imports this package

    ctx = build_context(project_id)
    out = sandbox.path("context")
    out.mkdir(parents=True, exist_ok=True)
    # newline="": these files are pushed verbatim to the Linux E2B sandbox, so writing them
    # with the host's default text-mode translation (CRLF on Windows) would corrupt them.
    (out / "brief.json").write_text(json.dumps(ctx["brief"], indent=2, ensure_ascii=False), encoding="utf-8", newline="")
    (out / "chosen_gap.json").write_text(json.dumps(ctx["gaps"]["chosen"], indent=2, ensure_ascii=False),
                                         encoding="utf-8", newline="")
    papers = [{k: p[k] for k in ("title", "year", "venue", "authors", "doi", "url", "notes")}
              for p in ctx["literature"]["papers"]]
    (out / "literature.json").write_text(json.dumps(
        {"overview": ctx["literature"]["overview"], "papers": papers}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8", newline="")
    with Session(engine) as s:
        plan = s.get(Project, project_id).plan
    if plan:
        (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8", newline="")


def prepare_states(project_id: str, bp_run_id: str, mp: dict) -> None:
    """Create task states on first run; on resume, retry what did not finish."""
    with Session(engine) as s:
        existing = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id))}
        for t in mp["tasks"]:
            st = existing.get(t["id"])
            if st is None:
                s.add(TaskState(project_id=project_id, blueprint_run_id=bp_run_id, task_id=t["id"], agent=t["agent"]))
            elif st.status in ("running", "cancelled", "blocked"):
                st.status, st.attempts = "pending", 0
                s.add(st)
            elif st.status == "failed":
                # Keep the attempt count so the retry escalates to a stronger model.
                st.status = "pending"
                s.add(st)
        s.commit()


async def run(project_id: str, h: RunHandle) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        bp_run = s.get(Run, project.blueprint["run_id"]) if project.blueprint else None
        if not bp_run:
            raise RuntimeError("Approve the blueprint first")
        # Read everything before commit(): committing expires loaded objects.
        mp, bp_run_id = bp_run.result["master_plan"], bp_run.id
        autonomous = project.autonomous
        # Scientific-review repairs run without guided checkpoints (they are applied automatically).
        repairing = (project.review or {}).get("status") in ("repairing", "attention")
        policy = (project.settings or {}).get("model_policy", "default")
        budget = float(((project.settings or {}).get("budget") or {}).get("llm_usd", 15.0))
        project.stage = "executing"
        s.add(project)
        s.commit()
    tasks = {t["id"]: t for t in mp["tasks"]}
    checkpoints = {} if autonomous or repairing else {c["after_task"]: c["reason"] for c in mp["checkpoints"]}
    capabilities = sandbox_for(project_id).capabilities
    prepare_states(project_id, bp_run_id, mp)
    load_secrets(project_id)

    ctl = Control()
    _controls[project_id] = ctl
    running: dict[str, asyncio.Task] = {}
    network_waits = 0  # automatic resumes since the last task that finished normally

    h.phase("preparing", "Setting up the workspace environment")
    sandbox = sandbox_for(project_id)
    await sandbox.ensure()
    _write_context(project_id, sandbox)
    if mp["python_packages"]:
        res = await sandbox.install(mp["python_packages"])
        h.note("Installed packages" if res.exit_code == 0 else f"Some packages failed to install: {res.stderr[-300:]}")
    h.phase("running", "Executing tasks")

    try:
        async with httpx.AsyncClient(headers={"User-Agent": "OpenScientist/0.1 (research agent)"}) as http:
            while True:
                if ctl.cancelled:
                    for t in running.values():
                        t.cancel()
                    await asyncio.gather(*running.values(), return_exceptions=True)
                    break

                with Session(engine) as s:
                    states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id))}

                # Settle tasks that cannot run on their own; repeat so blocks propagate down chains.
                changed = True
                while changed:
                    changed = False
                    for tid, st in states.items():
                        if st.status != "pending" or tid in running:
                            continue
                        deps = [states[d] for d in tasks[tid]["depends_on"] if d in states]
                        new = None
                        if any(d.status in ("failed", "blocked", "cancelled") for d in deps):
                            new = ("blocked", "Waiting on a failed or blocked upstream task")
                        elif all(d.status in SATISFIED for d in deps):
                            if tasks[tid]["human_required"]:
                                new = ("human", "Needs a person — mark done or skip")
                            elif tasks[tid]["compute"]["kind"] == "cuda_gpu" and "cuda_gpu" not in capabilities:
                                new = ("blocked", "Needs a CUDA GPU; this runtime has none")
                        if new:
                            _update(st.id, status=new[0], note=new[1])
                            st.status = new[0]
                            changed = True
                ready = [
                    tid for tid, st in states.items()
                    if st.status == "pending" and tid not in running
                    and all(states[d].status in SATISFIED for d in tasks[tid]["depends_on"] if d in states)
                ]

                total = spent(project_id)
                budget = current_budget(project_id)
                allowance = beta.project_allowance(project_id)  # owner's remaining beta allowance
                h.counts(**{k: sum(1 for st in states.values() if st.status == k)
                            for k in ("done", "running", "pending", "failed", "blocked", "human", "skipped")},
                         spent_cents=round(total * 100))
                if total >= budget and ctl.go.is_set():
                    ctl.pause(f"budget: ${total:.2f} of ${budget:.2f} spent")
                elif allowance <= 0 and ctl.go.is_set():
                    ctl.pause(beta.LIMIT_PAUSE)

                if not ctl.go.is_set():
                    if not running:
                        h.phase(f"paused:{ctl.reason}")
                        if ctl.reason.startswith(NETWORK_PAUSE) and network_waits < len(NETWORK_RETRY):
                            # Try again by itself. Still offline, a try stops at the fence or the first
                            # model request, which is not billed and uses up no attempt.
                            with contextlib.suppress(TimeoutError):
                                await asyncio.wait_for(ctl.go.wait(), NETWORK_RETRY[network_waits])
                            network_waits += 1
                            if not ctl.go.is_set() and (ctl.reason or "").startswith(NETWORK_PAUSE):
                                ctl.resume()
                        else:
                            await ctl.go.wait()
                        h.phase("running")
                        continue
                    ready = []  # let running tasks finish; start nothing new

                launch = ready[: max(0, MAX_PARALLEL - len(running))]
                for tid in launch:
                    running[tid] = asyncio.create_task(_execute(project_id, mp, tasks[tid], states[tid].id, policy, http))

                if not running:
                    if any(st.status == "human" for st in states.values()):
                        ctl.pause("human: a task needs a person")
                        continue
                    break  # nothing runnable remains

                done, _ = await asyncio.wait(running.values(), timeout=5, return_when=asyncio.FIRST_COMPLETED)
                for tid in [t for t, fut in running.items() if fut in done]:
                    fut = running.pop(tid)
                    if isinstance(fut.exception(), INFRASTRUCTURE):
                        # The connection failed, not the task: _execute re-queued it unchanged. Wait.
                        if ctl.go.is_set():
                            exc = fut.exception()
                            ctl.pause(f"{NETWORK_PAUSE}{type(exc).__name__}: {exc}"[:300])
                        continue
                    if fut.exception():
                        _update(states[tid].id, status="failed", note=f"Runtime error: {fut.exception()}", finished_at=_now())
                        continue
                    network_waits = 0
                    if tid in checkpoints:
                        with Session(engine) as s:
                            if s.get(TaskState, states[tid].id).status == "done":
                                ctl.pause(f"checkpoint:{tid}: {checkpoints[tid]}")
    finally:
        _controls.pop(project_id, None)
        stopped = sandbox.stop_all()  # background processes do not outlive the run
        if inspect.isawaitable(stopped):  # awaited, so a late kill cannot hit the next run's processes
            await stopped
        with Session(engine) as s:
            for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id, TaskState.status == "running")):
                st.status, st.note = "cancelled", "Execution stopped"
                s.add(st)
            s.commit()

    with Session(engine) as s:
        final = list(s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id)))
        counts = {k: sum(1 for st in final if st.status == k)
                  for k in ("done", "failed", "blocked", "skipped", "cancelled", "human")}
        total_tasks = len(final)
        project = s.get(Project, project_id)
        project.stage = "executed" if not ctl.cancelled else "ready"
        s.add(project)
        s.commit()
    h.note("Cancelled" if ctl.cancelled else f"Finished: {counts['done']} of {total_tasks} tasks done")
    return {"counts": counts, "spent": spent(project_id), "cancelled": ctl.cancelled}


# ── Human actions ──────────────────────────────────────────────────────────


def project_amendments(project_id: str) -> str:
    """All reviewer-approved amendments, oldest first, as text for prompts and verifiers."""
    with Session(engine) as s:
        items = (s.get(Project, project_id).settings or {}).get("amendments", [])
    return "\n\n".join(f"[{i + 1}] (via {a['task']}, {a['at'][:16]}) {a['text']}" for i, a in enumerate(items))


def _record_amendment(project_id: str, task_id: str, text: str) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        cfg = dict(project.settings or {})
        cfg["amendments"] = [*cfg.get("amendments", []), {"task": task_id, "text": text, "at": _now().isoformat()}]
        project.settings = cfg
        s.add(project)
        s.commit()
    out = sandbox_for(project_id).path("context")
    out.mkdir(parents=True, exist_ok=True)
    (out / "AMENDMENTS.md").write_text(
        "# Reviewer-approved protocol amendments\n\nThese override the plan and blueprint wherever they conflict.\n\n"
        + project_amendments(project_id) + "\n",
        encoding="utf-8", newline="",
    )


def request_changes(project_id: str, task_id: str, feedback: str) -> list[str]:
    """Re-run a finished task with reviewer feedback; downstream tasks that consumed its
    outputs are reset too. Returns the task ids that will re-run."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
        bp_run_id = project.blueprint["run_id"]
        tasks = {t["id"]: t for t in s.get(Run, bp_run_id).result["master_plan"]["tasks"]}
        states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_run_id))}
        if task_id not in states:
            raise LookupError(f"Unknown task {task_id}")
        if states[task_id].status == "running":
            raise ValueError(f"Task {task_id} is running")
        # Transitive dependents.
        reset, frontier = {task_id}, [task_id]
        while frontier:
            cur = frontier.pop()
            for tid, t in tasks.items():
                if cur in t["depends_on"] and tid not in reset:
                    reset.add(tid)
                    frontier.append(tid)
        for tid in reset:
            st = states[tid]
            if st.status == "running":
                raise ValueError(f"Dependent task {tid} is running; pause first")
            if st.status in ("done", "failed", "blocked", "cancelled", "pending"):
                st.status, st.attempts, st.note, st.checks = "pending", 0, None, []
                s.add(st)
        states[task_id].feedback = feedback
        s.add(states[task_id])
        s.commit()
    # Amendments apply to the whole study, not just this task: every later agent and check sees them.
    _record_amendment(project_id, task_id, feedback)
    ctl = control(project_id)
    if ctl and ctl.reason and ctl.reason.startswith("checkpoint"):
        ctl.resume()
    return sorted(reset)


def load_secrets(project_id: str) -> None:
    with Session(engine) as s:
        rows = s.exec(select(Secret).where(Secret.project_id == project_id)).all()
    sandbox_for(project_id).secrets = {r.name: r.value for r in rows}


def provide_secret(project_id: str, name: str, value: str) -> int:
    """Store a credential, expose it to the sandbox, and re-queue tasks waiting for it."""
    with Session(engine) as s:
        for old in s.exec(select(Secret).where(Secret.project_id == project_id, Secret.name == name)):
            s.delete(old)
        s.add(Secret(project_id=project_id, name=name, value=value))
        waiting = s.exec(select(TaskState).where(TaskState.project_id == project_id, TaskState.status == "human")).all()
        requeued = 0
        for st in waiting:
            if (st.note or "").startswith(f"Needs credential {name} "):
                st.status, st.note = "pending", None
                s.add(st)
                requeued += 1
        s.commit()
    load_secrets(project_id)
    ctl = control(project_id)
    if ctl and ctl.reason and ctl.reason.startswith("human"):
        ctl.resume()
    return requeued


def set_task_status(project_id: str, task_id: str, status: str, note: str | None) -> TaskState:
    """Mark a task done (a human task, or accepting a failed task's output) or skip it,
    then let the scheduler reconsider anything it was blocking."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
        st = s.exec(select(TaskState).where(
            TaskState.blueprint_run_id == project.blueprint["run_id"], TaskState.task_id == task_id
        )).first()
        if st is None:
            raise LookupError(f"Unknown task {task_id}")
        if st.status in ("running", "done"):
            raise ValueError(f"Task {task_id} is {st.status}")
        st.status, st.note, st.finished_at = status, note, _now()
        s.add(st)
        # Blocked tasks are re-evaluated; any still blocked by something else re-block.
        for other in s.exec(select(TaskState).where(TaskState.blueprint_run_id == st.blueprint_run_id,
                                                     TaskState.status == "blocked")):
            if not (other.note or "").startswith("Needs a CUDA"):
                other.status = "pending"
                s.add(other)
        s.commit()
        s.refresh(st)
    ctl = control(project_id)
    if ctl and ctl.reason and ctl.reason.startswith("human"):
        ctl.resume()
    return st
