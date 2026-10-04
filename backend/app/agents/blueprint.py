"""Stage 5 · Blueprint.

Compiles the approved research plan into `master_plan.json`: the agent team,
executable tasks with exact inputs/outputs and acceptance checks, datasets with
verified sources, and human checkpoints. Validated in code against the tool
registry, the runtime's capabilities and the task graph.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import Project, Run, engine
from ..execution import catalog
from ..execution.sandbox import _PKG, sandbox_for
from ..execution.tools import TOOLS, public_url, describe
from ..jobs import RunHandle
from ..llm import parse
from .plan import EXPORT_DIR

DEFAULT_BUDGET = {"llm_usd": 15.0, "gpu_hours": 5.0}


# ── Schemas ────────────────────────────────────────────────────────────────


class ResolvedDataset(BaseModel):
    name: str = Field(description="Name as in the plan")
    url: str | None = Field(description="Direct download or API/landing URL; null if not found")
    access_method: str = Field(description="How an agent fetches it: download_file, http_request to an API, a pip loader…")
    format: str
    size_estimate: str
    license: str
    notes: str = Field(description="Caveats: auth needed, partial coverage, alternative sources")


class Resolution(BaseModel):
    datasets: list[ResolvedDataset]


class AgentDef(BaseModel):
    id: str = Field(description="'A1', 'A2', …")
    name: str = Field(description="Role, e.g. 'Data engineer', 'Statistician'")
    model_tier: Literal["reasoning", "standard", "bulk"] = Field(
        description="reasoning only for hard analysis/design; standard for most work; bulk for simple repetitive work"
    )
    tools: list[str]
    instructions: str = Field(description="3-6 sentences specialising this agent")


class TaskInput(BaseModel):
    path: str
    source: str = Field(description="'task:<id>' (an upstream output), 'dataset:<id>', or 'workspace'")


class TaskOutput(BaseModel):
    path: str = Field(description="Workspace-relative path, e.g. 'data/clean/measurements.parquet'")
    format: str
    description: str


class Compute(BaseModel):
    kind: Literal["cpu", "apple_gpu", "cuda_gpu"]
    est_minutes: int
    timeout_minutes: int


class ExecTask(BaseModel):
    id: str = Field(description="Same id as the plan task")
    title: str
    agent: str = Field(description="Agent id")
    objective: str
    steps: list[str] = Field(description="Ordered, concrete steps")
    inputs: list[TaskInput]
    outputs: list[TaskOutput]
    acceptance_checks: list[str] = Field(description="Verifiable conditions on the outputs")
    depends_on: list[str]
    tools: list[str]
    resources: list[str] = Field(description="Catalog resource names or dataset ids used")
    compute: Compute
    max_cost_usd: float = Field(description="Estimated LLM cost (USD) for this task; informational, not a limit")
    retries: int
    human_required: bool = Field(description="True if a person must do this (lab, fieldwork, credentials)")


class Checkpoint(BaseModel):
    after_task: str
    reason: str


class DatasetSpec(BaseModel):
    id: str = Field(description="'D1', 'D2', …")
    name: str
    url: str | None
    access_method: str
    format: str
    license: str
    notes: str


class MasterPlan(BaseModel):
    title: str
    summary: str = Field(description="How the agents will execute the study, 3-5 sentences")
    python_packages: list[str] = Field(description="pip requirement specs for the workspace")
    system_requirements: list[str] = Field(description="Non-pip needs (binaries, GPUs, accounts); [] if none")
    agents: list[AgentDef]
    datasets: list[DatasetSpec]
    tasks: list[ExecTask]
    checkpoints: list[Checkpoint] = Field(description="Points where a human should review results in guided mode")
    llm_usd_estimate: float
    compute_hours_estimate: float
    execution_notes: list[str]


RESOLVE_INSTRUCTIONS = """\
You locate the real sources for datasets in a research plan. Use web search. For
each dataset give a URL that actually hosts it (download link, API endpoint or
landing page with download instructions), how an automated agent would fetch it,
format, rough size, license. If you cannot find it, set url to null and suggest
alternatives in notes. Never invent URLs."""

COMPILE_INSTRUCTIONS = """\
You are the Blueprint Agent of OpenScientist. Compile the approved research plan
into an exact execution blueprint for a team (a swarm) of autonomous agents working
in a shared project workspace. Research may be in any field, on any topic, with any
tool or server. Agents are NOT limited to the resource catalog: they can find any
service or software with web_search/read_webpage, call it with http_request or
their own client code, install software via pip or conda (conda-forge/bioconda),
download and build tools, run long jobs as background processes, fan work out to
parallel sub-agents, share findings through team notes, and ask the user for an
API key when a service requires one.

Rules:
- One ExecTask per plan task (same ids), unless a plan task must be split; keep
  dependencies consistent with inputs.
- Every input is either an upstream task output (source 'task:<id>', and that task
  must be in depends_on and list the same path as an output), a dataset
  ('dataset:<id>'), or 'workspace'.
- Outputs use stable workspace paths (data/, analysis/, figures/, paper/).
- Acceptance checks must be checkable by reading the outputs.
- Only use tools from the tool list; respect UNAVAILABLE tools and the runtime
  capabilities. Mark tasks needing a person as human_required.
- Design the team for the work: 2-12 agents with focused roles (e.g. data
  engineers, domain specialists, ML/simulation engineers, statisticians, writers)
  and the tools each role needs. Use the 'reasoning' tier only for hard design,
  debugging or analysis.
- Maximise parallelism: split work into fine-grained tasks so independent tasks run
  at the same time, and give tasks with many independent units (sweeps, ablations,
  per-target or per-dataset runs) the spawn_subagents tool, describing the fan-out in
  the steps.
- Code-heavy tasks should write real modules and tests (src/, tests/) and run them;
  long computations use start_process + check_process.
- Do not re-review the literature: the Literature and Gaps stages already did, and
  their results are in the workspace under context/. Agents may look up a specific
  fact they need, but no task exists only to survey or verify prior work.
- Do not include paper-writing tasks: the Report stage writes the paper from the
  execution outputs. The last task produces publication figures (PNG), tables and a
  results summary (results/SUMMARY.md) with the key numbers.
- Every task must advance the science (data, code, experiments, analysis, figures).
  Fold bookkeeping (provenance, configs, logging) into those tasks instead of
  separate audit/protocol tasks. Prefer 5-10 substantive tasks.
- Put experiment grids in code and run them as background processes (or fan them
  out with spawn_subagents), so LLM cost stays low while compute does the work.
- Estimate costs honestly and keep the total LLM estimate within the budget.
- In checkpoints, add human reviews after data acquisition and before the paper.
- Software: prefer pip (install_packages), then conda-forge/bioconda
  (install_conda_packages) for binaries such as docking, MD, alignment or FEM tools.
  If the plan names something neither provides (e.g. MATLAB), substitute an
  equivalent and say so in execution_notes.
- system_requirements lists only needs this runtime does NOT already meet.
- datasets lists external sources only, never the study's own derived outputs."""


# ── Validation ─────────────────────────────────────────────────────────────


def validate(mp: MasterPlan, capabilities: set[str], budget: dict) -> tuple[list[str], list[str]]:
    """Returns (errors that must be fixed, warnings to surface to the user)."""
    errors: list[str] = []
    warnings: list[str] = []
    agents = {a.id: a for a in mp.agents}
    tasks = {t.id: t for t in mp.tasks}
    datasets = {d.id for d in mp.datasets}

    if len(tasks) != len(mp.tasks):
        errors.append("Duplicate task ids")
    for a in mp.agents:
        unknown = [t for t in a.tools if t not in TOOLS]
        if unknown:
            errors.append(f"Agent {a.id} uses unknown tools: {', '.join(unknown)}")
    for spec in mp.python_packages:
        if not _PKG.match(spec):
            errors.append(f"Invalid package spec '{spec}'")

    # Ancestors, for checking that inputs come from upstream tasks.
    def ancestors(tid: str, seen: set[str] | None = None) -> set[str]:
        seen = seen if seen is not None else set()
        for d in tasks[tid].depends_on:
            if d in tasks and d not in seen:
                seen.add(d)
                ancestors(d, seen)
        return seen

    for t in mp.tasks:
        if t.agent not in agents:
            errors.append(f"{t.id} is assigned to unknown agent {t.agent}")
        else:
            extra = [x for x in t.tools if x not in agents[t.agent].tools]
            if extra:
                errors.append(f"{t.id} uses tools its agent {t.agent} lacks: {', '.join(extra)}")
        for d in t.depends_on:
            if d not in tasks:
                errors.append(f"{t.id} depends on unknown task {d}")
        if not t.outputs and not t.human_required:
            errors.append(f"{t.id} produces no outputs")
        for inp in t.inputs:
            kind, _, ref = inp.source.partition(":")
            if kind == "task":
                if ref not in tasks:
                    errors.append(f"{t.id} input {inp.path} comes from unknown task {ref}")
                elif ref not in ancestors(t.id):
                    errors.append(f"{t.id} uses {inp.path} from {ref} but does not depend on it")
                elif all(o.path != inp.path for o in tasks[ref].outputs):
                    errors.append(f"{t.id} expects {inp.path} but {ref} does not produce it")
            elif kind == "dataset" and ref not in datasets:
                errors.append(f"{t.id} uses unknown dataset {ref}")
            elif kind not in ("task", "dataset", "workspace"):
                errors.append(f"{t.id} input {inp.path} has an invalid source '{inp.source}'")

    # Cycles (Kahn).
    deps = {tid: {d for d in t.depends_on if d in tasks} for tid, t in tasks.items()}
    ready = [i for i, d in deps.items() if not d]
    seen = 0
    while ready:
        n = ready.pop()
        seen += 1
        for i, d in deps.items():
            if n in d:
                d.discard(n)
                if not d:
                    ready.append(i)
    if seen < len(deps):
        errors.append("Task dependencies contain a cycle")

    # Runtime feasibility: flagged, not fatal — the user decides.
    for t in mp.tasks:
        if t.human_required:
            warnings.append(f"{t.id} needs a person: {t.title}")
        if t.compute.kind == "cuda_gpu" and "cuda_gpu" not in capabilities:
            warnings.append(f"{t.id} needs a CUDA GPU, which this runtime lacks (cloud runner required)")
        if t.compute.kind == "apple_gpu" and "apple_gpu" not in capabilities:
            warnings.append(f"{t.id} needs an Apple GPU, which this runtime lacks")
        blocked = [x for x in t.tools if x in TOOLS and not set(TOOLS[x].requires) <= capabilities]
        if blocked:
            warnings.append(f"{t.id} needs tools unavailable here: {', '.join(blocked)}")
    for req in mp.system_requirements:
        warnings.append(f"System requirement: {req}")
    for d in mp.datasets:
        if not d.url:
            warnings.append(f"Dataset {d.id} ({d.name}) has no confirmed source")
    total = sum(t.max_cost_usd for t in mp.tasks)
    if total > budget["llm_usd"]:
        warnings.append(f"Task cost estimates total ${total:.2f}, above the ${budget['llm_usd']:.2f} project budget")
    gpu_hours = sum(t.compute.est_minutes for t in mp.tasks if t.compute.kind != "cpu") / 60
    if gpu_hours > budget["gpu_hours"]:
        warnings.append(f"Estimated {gpu_hours:.1f} GPU-hours exceeds the {budget['gpu_hours']} h budget")
    return errors, warnings


async def _verify_urls(datasets: list[DatasetSpec]) -> dict[str, bool]:
    """Check that dataset URLs are reachable (HEAD, falling back to a ranged GET)."""

    async def check(client: httpx.AsyncClient, url: str) -> bool:
        try:
            public_url(url)
            r = await client.head(url, follow_redirects=True, timeout=20)
            if r.status_code in (403, 405) or r.status_code >= 500:
                r = await client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True, timeout=20)
            # API endpoints often answer 4xx without parameters; that still proves they exist.
            return r.status_code < 400 or r.status_code in (400, 401, 403, 405, 422, 429)
        except Exception:
            return False

    async with httpx.AsyncClient(headers={"User-Agent": "OpenScientist/0.1 (research agent)"}) as client:
        results = await asyncio.gather(*(check(client, d.url) for d in datasets if d.url))
    return dict(zip([d.id for d in datasets if d.url], results))


# ── Job ────────────────────────────────────────────────────────────────────


def _budget(project: Project) -> dict:
    return {**DEFAULT_BUDGET, **(project.settings or {}).get("budget", {})}


async def run(project_id: str, h: RunHandle) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
    if not project.plan:
        raise RuntimeError("Approve the research plan first")
    plan = {k: v for k, v in project.plan.items() if k not in ("run_id", "approved_at", "schema")}
    capabilities = sandbox_for(project_id).capabilities
    budget = _budget(project)

    # 1 · Resolve datasets (web search; standard tier is plenty)
    h.phase("resolving", f"Locating sources for {len(plan['datasets'])} datasets")
    resolution = await parse(
        model=settings.model_standard,
        instructions=RESOLVE_INSTRUCTIONS,
        messages=[{"role": "user", "content": f"Research question: {plan['research_question']}\n\nDatasets:\n"
                   + json.dumps(plan["datasets"], ensure_ascii=False)}],
        schema=Resolution,
        reasoning_effort="low",
        tools=[{"type": "web_search"}],
    )
    found = sum(1 for d in resolution.datasets if d.url)
    h.note(f"Found sources for {found} of {len(resolution.datasets)} datasets")

    # 2 · Compile
    h.phase("compiling", "Designing the agent team and executable tasks")
    context = (
        f"APPROVED PLAN:\n{json.dumps(plan, ensure_ascii=False)}\n\n"
        f"RESOLVED DATASETS:\n{resolution.model_dump_json()}\n\n"
        f"TOOLS:\n{describe(capabilities)}\n\n"
        f"RUNTIME CAPABILITIES: {', '.join(sorted(capabilities))} (no Apple GPU, no CUDA GPU; "
        "conda available; background processes; ~1 GB per download; small disk)\n\n"
        f"BUDGET: ${budget['llm_usd']:.2f} LLM, {budget['gpu_hours']} GPU-hours\n\n"
        f"RESOURCE CATALOG:\n{catalog.summary()}"
    )
    mp = await parse(
        model=settings.model_reasoning,
        instructions=COMPILE_INSTRUCTIONS,
        messages=[{"role": "user", "content": context}],
        schema=MasterPlan,
        reasoning_effort="medium",
    )

    # 3 · Validate, with one repair pass
    h.phase("validating", "Checking tools, inputs/outputs, dependencies and budget")
    errors, warnings = validate(mp, capabilities, budget)
    if errors:
        h.phase("repairing", f"Fixing {len(errors)} structural problems")
        mp = await parse(
            model=settings.model_standard,
            instructions=COMPILE_INSTRUCTIONS + "\nYou are repairing a blueprint: change only what the errors require.",
            messages=[{"role": "user", "content": "Fix these problems:\n- " + "\n- ".join(errors)
                       + f"\n\nTools:\n{describe(capabilities)}\n\nBlueprint:\n{mp.model_dump_json()}"}],
            schema=MasterPlan,
            reasoning_effort="low",
        )
        errors, warnings = validate(mp, capabilities, budget)
        if errors:
            raise RuntimeError("Blueprint still invalid after repair: " + "; ".join(errors[:5]))

    verified = await _verify_urls(mp.datasets)
    data = mp.model_dump()
    for d in data["datasets"]:
        d["verified"] = verified.get(d["id"], False)
        if d["url"] and not d["verified"]:
            warnings.append(f"Dataset {d['id']} URL did not respond: {d['url']}")
    h.counts(agents=len(mp.agents), tasks=len(mp.tasks), warnings=len(warnings))
    h.note("Blueprint ready for review")
    return {"master_plan": data, "warnings": warnings, "capabilities": sorted(capabilities), "budget": budget,
            "plan_run_id": project.plan["run_id"]}


def latest_run(project_id: str) -> Run | None:
    with Session(engine) as s:
        return s.exec(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "blueprint", Run.status == "done")
            .order_by(Run.started_at.desc())
        ).first()


def make_revision_job(instruction: str):
    async def revise(project_id: str, h: RunHandle) -> dict:
        prev = latest_run(project_id)
        if not prev:
            raise RuntimeError("No blueprint to revise")
        with Session(engine) as s:
            project = s.get(Project, project_id)
        capabilities = sandbox_for(project_id).capabilities
        budget = _budget(project)
        h.phase("compiling", "Revising the blueprint")
        policy = (project.settings or {}).get("model_policy", "default")
        mp = await parse(
            model=settings.model_bulk if policy == "minimal" else settings.model_standard,
            instructions=COMPILE_INSTRUCTIONS + "\nRevise the blueprint per the instruction; keep everything else.",
            messages=[{"role": "user", "content": f"Instruction: {instruction}\n\nTools:\n{describe(capabilities)}"
                       f"\n\nBlueprint:\n{json.dumps(prev.result['master_plan'])}"}],
            schema=MasterPlan,
            reasoning_effort="medium",
        )
        h.phase("validating", "Checking the revised blueprint")
        errors, warnings = validate(mp, capabilities, budget)
        if errors:
            raise RuntimeError("Revision produced an invalid blueprint: " + "; ".join(errors[:5]))
        verified = await _verify_urls(mp.datasets)
        data = mp.model_dump()
        for d in data["datasets"]:
            d["verified"] = verified.get(d["id"], False)
            if d["url"] and not d["verified"]:
                warnings.append(f"Dataset {d['id']} URL did not respond: {d['url']}")
        h.counts(agents=len(mp.agents), tasks=len(mp.tasks), warnings=len(warnings))
        return {**prev.result, "master_plan": data, "warnings": warnings, "instruction": instruction}

    return revise


def approve(project_id: str) -> Project:
    run = latest_run(project_id)
    if not run:
        raise LookupError("No blueprint to approve")
    doc = {"schema": "openscientist.master_plan/v1", **run.result["master_plan"],
           "warnings": run.result["warnings"], "budget": run.result["budget"]}
    out = EXPORT_DIR / project_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "master_plan.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project.blueprint = {"run_id": run.id, "approved_at": datetime.now(timezone.utc).isoformat()}
        project.stage = "ready"
        s.add(project)
        s.commit()
        s.refresh(project)
        return project
