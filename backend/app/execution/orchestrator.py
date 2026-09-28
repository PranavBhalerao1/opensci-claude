"""Stage 6 · Execution: run master_plan.json.

Schedules blueprint tasks in dependency order (parallel where possible), runs
each with its agent in the project sandbox, verifies outputs (existence in
code, acceptance checks by a cheap model), retries with feedback, and enforces
the project budget. Guided mode pauses at human checkpoints. State lives in the
TaskState table, so a restarted server resumes where it left off.
"""

import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..db import Project, Run, Secret, TaskState, Usage, engine
from ..jobs import RunHandle
from ..llm import parse
from . import catalog
from .agent import AgentSpec, run_agent
from .sandbox import sandbox_for
from .tools import TOOLS, ToolContext

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
ESCALATED_MIN_BUDGET = 0.12  # a stronger model needs room to debug


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


def _task_prompt(mp: dict, task: dict, states: dict[str, TaskState], feedback: str | None) -> str:
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
            rows = p.read_text(errors="replace").splitlines()
            head, body = rows[0], rows[1:]
            sample = body[:12] + (["…"] + body[-5:] if len(body) > 17 else body[12:])
            blocks.append(
                f"### {o['path']} ({size:,} bytes)\nFACTS: {len(body):,} data rows (excluding the header); "
                f"columns: {head}\nFirst and last rows:\n{head}\n" + "\n".join(sample)
            )
        elif p.suffix.lower() in TEXT_SUFFIXES and size:
            text = p.read_text(errors="replace")
            lines = text.count("\n")
            if len(text) > PREVIEW_CHARS:
                head, tail = PREVIEW_CHARS * 2 // 3, PREVIEW_CHARS // 3
                text = f"{text[:head]}\n… [{len(text) - PREVIEW_CHARS:,} chars omitted] …\n{text[-tail:]}"
            blocks.append(f"### {o['path']} ({size:,} bytes, {lines:,} lines)\n{text}")
        else:
            blocks.append(f"### {o['path']} ({size:,} bytes, binary {p.suffix or 'file'}; content not shown)")
    return "\n\n".join(blocks)


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


async def _verify(task: dict, sandbox, policy: str, report: dict | None = None) -> list[dict]:
    if not task["acceptance_checks"]:
        return []
    evidence = "Output previews:\n" + _previews(sandbox, task["outputs"])
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
        reasoning_effort="low",
    )
    return [r.model_dump() for r in verdict.results]


def _task_tools(task: dict, agent: dict, sandbox) -> list[str]:
    tools = [t for t in task["tools"] if t in agent["tools"] and t in TOOLS] or list(agent["tools"])
    # GPU work goes to cloud GPUs when they are available, even if the blueprint predates them.
    if task["compute"]["kind"] in ("cuda_gpu", "apple_gpu") and "cuda_gpu" in sandbox.capabilities:
        tools += [t for t in ("run_gpu_jobs",) if t not in tools]
    return tools


def _subagent_runner(spec: AgentSpec, ctx: ToolContext, state_id: str, budget: float, cost_box: list[float]):
    """Build the spawn callback: children share the workspace, cannot spawn further, split the budget."""

    async def spawn(subtasks: list[dict]) -> list[dict]:
        child_budget = max(0.03, budget * 0.7 / len(subtasks))
        child_tools = [t for t in spec.tools if t != "spawn_subagents"]

        async def one(sub: dict) -> dict:
            name = re.sub(r"[^A-Za-z0-9_-]", "_", sub["name"])[:30]
            child = AgentSpec(
                name=f"{spec.name} › {name}", instructions=spec.instructions, model=spec.model, tools=child_tools,
                max_steps=MAX_AGENT_STEPS, max_cost=child_budget, reasoning_effort=spec.reasoning_effort,
            )
            child_ctx = ToolContext(ctx.project_id, ctx.sandbox, ctx.http, agent_name=child.name)
            task = sub["instructions"] + "\n\nRequired outputs:\n" + "\n".join(f"- {o}" for o in sub["outputs"])
            res = await run_agent(child, task, child_ctx,
                                  on_event=lambda e: _append_event(state_id, {**e, "sub": name}))
            cost_box[0] += res.cost
            missing = [o for o in sub["outputs"] if not ctx.sandbox.path(o).exists()]
            return {"name": name, "status": res.status, "summary": res.summary, "artifacts": res.artifacts,
                    "metrics": res.metrics, "missing_outputs": missing, "cost": round(res.cost, 4)}

        _append_event(state_id, {"type": "message", "step": 0, "text": f"Spawning {len(subtasks)} sub-agents",
                                 "cost": 0.0})
        return list(await asyncio.gather(*(one(s) for s in subtasks)))

    return spawn


async def _execute(project_id: str, mp: dict, task: dict, state_id: str, policy: str, http: httpx.AsyncClient,
                   remaining: float = float("inf")) -> None:
    with Session(engine) as s:
        states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == s.get(TaskState, state_id).blueprint_run_id))}
    me = next(st for st in states.values() if st.id == state_id)
    feedback = me.note if me.attempts else None
    if me.feedback:
        feedback = f"REVIEWER-APPROVED CHANGE (overrides earlier protocol where they conflict):\n{me.feedback}"
    _update(state_id, status="running", attempts=me.attempts + 1, started_at=_now(), finished_at=None, feedback=None)

    agent = next(a for a in mp["agents"] if a["id"] == task["agent"])
    sandbox = sandbox_for(project_id)
    model, escalated = escalated_model(agent["model_tier"], policy, me.attempts + 1)
    if escalated:
        _append_event(state_id, {"type": "message", "step": 0, "text": f"Retrying with a stronger model ({model})",
                                 "cost": 0.0})
    spec = AgentSpec(
        name=f"{agent['name']} ({task['id']})",
        instructions=COMMON_INSTRUCTIONS.format(
            name=agent["name"], role=agent["instructions"], today=_now().date().isoformat()
        ),
        model=model,
        tools=_task_tools(task, agent, sandbox),
        max_steps=MAX_AGENT_STEPS,
        # Never let one task spend beyond what is left of the project budget.
        max_cost=min(max(ESCALATED_MIN_BUDGET if escalated else 0.05, float(task["max_cost_usd"])), max(0.02, remaining)),
        reasoning_effort="medium" if escalated else ("low" if agent["model_tier"] == "bulk" or policy == "minimal" else "medium"),
    )
    ctx = ToolContext(project_id, sandbox, http, agent_name=agent["name"])
    sub_cost = [0.0]
    if "spawn_subagents" in spec.tools:
        ctx.spawn = _subagent_runner(spec, ctx, state_id, spec.max_cost, sub_cost)
    res = await run_agent(spec, _task_prompt(mp, task, states, feedback), ctx,
                          on_event=lambda e: _append_event(state_id, e))

    if res.status == "needs_credential":
        c = res.credential
        _update(
            state_id, status="human", attempts=me.attempts, cost=me.cost + res.cost + sub_cost[0],
            note=f"Needs credential {c['env_var']} for {c['service']}: {c['reason']}"
                 + (f" Sign up: {c['signup_url']}" if c.get("signup_url") else ""),
            finished_at=_now(),
        )
        return

    missing = [o["path"] for o in task["outputs"] if not sandbox.path(o["path"]).exists()]
    report = {"status": res.status, "summary": res.summary, "metrics": res.metrics, "issues": res.issues}
    # Verify whenever every output exists — an agent cut off by its budget or step limit
    # may already have finished the work. An explicit "failed" report is trusted.
    verifiable = not missing and res.status != "failed"
    checks = await _verify(task, sandbox, policy, report) if verifiable else []
    passed = verifiable and bool(checks or not task["acceptance_checks"]) and all(c["passed"] for c in checks)
    if passed and res.status in ("budget_exceeded", "step_limit"):
        res.issues.append(f"Agent stopped ({res.status}) before reporting; outputs verified by the platform.")
    problems = (
        [f"Missing outputs: {', '.join(missing)}"] if missing else []
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
    (out / "brief.json").write_text(json.dumps(ctx["brief"], indent=2, ensure_ascii=False))
    (out / "chosen_gap.json").write_text(json.dumps(ctx["gaps"]["chosen"], indent=2, ensure_ascii=False))
    papers = [{k: p[k] for k in ("title", "year", "venue", "authors", "doi", "url", "notes")}
              for p in ctx["literature"]["papers"]]
    (out / "literature.json").write_text(json.dumps(
        {"overview": ctx["literature"]["overview"], "papers": papers}, indent=2, ensure_ascii=False, default=str))
    with Session(engine) as s:
        plan = s.get(Project, project_id).plan
    if plan:
        (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False, default=str))


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
        policy = (project.settings or {}).get("model_policy", "default")
        budget = float(((project.settings or {}).get("budget") or {}).get("llm_usd", 15.0))
        project.stage = "executing"
        s.add(project)
        s.commit()
    tasks = {t["id"]: t for t in mp["tasks"]}
    checkpoints = {} if autonomous else {c["after_task"]: c["reason"] for c in mp["checkpoints"]}
    capabilities = sandbox_for(project_id).capabilities
    prepare_states(project_id, bp_run_id, mp)
    load_secrets(project_id)

    ctl = Control()
    _controls[project_id] = ctl
    running: dict[str, asyncio.Task] = {}

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
                h.counts(**{k: sum(1 for st in states.values() if st.status == k)
                            for k in ("done", "running", "pending", "failed", "blocked", "human", "skipped")},
                         spent_cents=round(total * 100))
                if total >= budget and ctl.go.is_set():
                    ctl.pause(f"budget: ${total:.2f} of ${budget:.2f} spent")

                if not ctl.go.is_set():
                    if not running:
                        h.phase(f"paused:{ctl.reason}")
                        await ctl.go.wait()
                        h.phase("running")
                        continue
                    ready = []  # let running tasks finish; start nothing new

                launch = ready[: max(0, MAX_PARALLEL - len(running))]
                # Split what is left of the budget between the tasks starting now and those running.
                share = max(0.0, budget - total) / max(1, len(launch) + len(running))
                for tid in launch:
                    running[tid] = asyncio.create_task(
                        _execute(project_id, mp, tasks[tid], states[tid].id, policy, http, remaining=share)
                    )

                if not running:
                    if any(st.status == "human" for st in states.values()):
                        ctl.pause("human: a task needs a person")
                        continue
                    break  # nothing runnable remains

                done, _ = await asyncio.wait(running.values(), timeout=5, return_when=asyncio.FIRST_COMPLETED)
                for tid in [t for t, fut in running.items() if fut in done]:
                    fut = running.pop(tid)
                    if fut.exception():
                        _update(states[tid].id, status="failed", note=f"Runtime error: {fut.exception()}", finished_at=_now())
                    elif tid in checkpoints:
                        with Session(engine) as s:
                            if s.get(TaskState, states[tid].id).status == "done":
                                ctl.pause(f"checkpoint:{tid}: {checkpoints[tid]}")
    finally:
        _controls.pop(project_id, None)
        sandbox.stop_all()  # background processes do not outlive the run
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
