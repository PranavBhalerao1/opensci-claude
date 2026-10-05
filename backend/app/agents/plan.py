"""Stage 4 · Research plan.

Drafts `vague_research_plan.json` for the chosen gap (flagship model), validates
the task graph in code (unique ids, known dependencies, no cycles) with one
repair pass, and on approval exports it with `context.json` — the Planning
Agent's hand-off to the Blueprint Agent.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from ..config import BACKEND_DIR, settings
from ..db import Message, Paper, Project, ProjectPaper, Run, engine
from ..graph import project_graph
from ..jobs import RunHandle
from ..llm import parse
from .literature import brief_context, cite

EXPORT_DIR = BACKEND_DIR / "data" / "projects"
EXPORT_FILES = ("vague_research_plan.json", "context.json", "master_plan.json")


# ── Schema (vague_research_plan.json) ──────────────────────────────────────


class Task(BaseModel):
    id: str = Field(description="'T<phase>.<n>', e.g. T1.2")
    title: str
    description: str = Field(description="2-4 sentences: what to do and how, concretely")
    kind: Literal[
        "data_acquisition", "data_processing", "analysis", "modeling", "experiment", "evaluation", "literature", "writing"
    ]
    inputs: list[str] = Field(description="Data or artifacts consumed (by name)")
    outputs: list[str] = Field(description="Artifacts produced, as file-like names, e.g. 'splits.parquet'")
    depends_on: list[str] = Field(description="Task ids that must finish first")
    effort: Literal["S", "M", "L"]
    tools_hint: list[str] = Field(description="Likely libraries/tools, e.g. 'pandas', 'PyTorch', 'scikit-learn'")


class Phase(BaseModel):
    id: str = Field(description="'P1', 'P2', …")
    name: str
    goal: str
    tasks: list[Task]


class Dataset(BaseModel):
    name: str
    description: str
    source: str = Field(description="URL only if well known or in the notes, else 'to be located'")
    access: Literal["public", "request", "user_provided", "unknown"]
    role: str = Field(description="How the study uses it")


class Method(BaseModel):
    name: str
    purpose: str


class Metric(BaseModel):
    name: str
    definition: str
    success_threshold: str = Field(description="What value or comparison counts as success")


class Risk(BaseModel):
    risk: str
    likelihood: Literal["low", "medium", "high"]
    mitigation: str


class ResearchPlan(BaseModel):
    title: str
    research_question: str
    hypothesis: str
    null_hypothesis: str
    objectives: list[str]
    background: str = Field(description="One paragraph motivating the study, citing papers as [index]")
    study_type: Literal["empirical", "computational", "theoretical", "benchmark", "meta_analysis"]
    phases: list[Phase] = Field(description="3-6 phases from data to write-up")
    datasets: list[Dataset]
    methods: list[Method]
    baselines: list[str]
    metrics: list[Metric]
    validation_strategy: str = Field(description="Splits, controls, statistics, robustness checks")
    success_criteria: list[str]
    compute_estimate: str = Field(description="Hardware and rough GPU/CPU hours")
    duration_estimate: str = Field(description="Rough wall-clock for autonomous execution")
    risks: list[Risk]
    deliverables: list[str] = Field(description="Figures, tables, datasets, and the paper")
    open_questions: list[str] = Field(description="Assumptions to verify early in execution")


PLAN_INSTRUCTIONS = """\
You are the Planning Agent of OpenScientist. Write the research plan for the chosen
gap. It will be expanded by a Blueprint Agent into an exact execution spec for
autonomous agents that write and run code, query scientific databases and APIs in
any field, install domain software (e.g. bioinformatics, cheminformatics, CAD,
simulation, GIS, statistics packages) and search the web. So:
- Every task must be concrete and executable by an agent: state what to do, with
  what data, producing which named artifacts. No wet-lab or human-subject steps.
- Wire dependencies explicitly; parallelise independent work.
- Design experiments strong enough for peer review: proper baselines and ablations,
  at least 3-5 independent seeds (or resamples) per condition, effect sizes with
  confidence intervals, and a pre-stated primary comparison. Size the experiments
  to what the compute estimate can actually run.
- Spend the effort on science: one focused, decisive main result plus supporting
  analyses beats many small checks. Do not create tasks whose only purpose is
  process (protocol freezing, audits, sign-offs); fold such steps into the
  scientific tasks that need them.
- Final phase: figures, tables and a conference-style paper draft.
- Be honest about uncertainty; put unverified assumptions in open_questions.
Cite papers only by [index]."""

REVISE_INSTRUCTIONS = """\
Revise the research plan according to the user's instruction. Keep everything the
instruction does not touch. Keep task ids stable where tasks are unchanged and keep
the dependency graph valid."""


# ── Validation ─────────────────────────────────────────────────────────────


def graph_errors(plan: ResearchPlan) -> list[str]:
    """Structural problems in the task graph, as human-readable strings."""
    errors: list[str] = []
    tasks = [t for ph in plan.phases for t in ph.tasks]
    ids = [t.id for t in tasks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"Duplicate task ids: {', '.join(sorted(dupes))}")
    known = set(ids)
    for t in tasks:
        for d in t.depends_on:
            if d not in known:
                errors.append(f"{t.id} depends on unknown task {d}")
            if d == t.id:
                errors.append(f"{t.id} depends on itself")
    # Cycle check (Kahn).
    deps = {t.id: {d for d in t.depends_on if d in known and d != t.id} for t in tasks}
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
        errors.append("The task dependencies contain a cycle")
    if not tasks:
        errors.append("The plan has no tasks")
    return errors


def prune_bad_deps(plan: ResearchPlan) -> None:
    known = {t.id for ph in plan.phases for t in ph.tasks}
    for ph in plan.phases:
        for t in ph.tasks:
            t.depends_on = [d for d in dict.fromkeys(t.depends_on) if d in known and d != t.id]


def parse_plan(data: dict) -> tuple[ResearchPlan | None, list[str]]:
    """Validate user-edited plan JSON against the schema and the task graph."""
    try:
        plan = ResearchPlan.model_validate(data)
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:8]]
    return plan, graph_errors(plan)


# ── Context ────────────────────────────────────────────────────────────────


def _load(project_id: str):
    with Session(engine) as s:
        project = s.get(Project, project_id)
        rows = s.exec(
            select(ProjectPaper, Paper)
            .join(Paper, Paper.id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
            .order_by(ProjectPaper.relevance.desc(), ProjectPaper.score.desc())
        ).all()
        lit = s.exec(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "literature", Run.status == "done")
            .order_by(Run.started_at.desc())
        ).first()
    return project, rows, lit


def _plan_context(project: Project, rows, lit: Run) -> tuple[str, list[Paper]]:
    gap = project.chosen_gap
    overview = lit.result["overview"]
    supporting = set(gap["supporting_paper_ids"])
    papers = [p for _, p in rows if p.notes]
    # Motivating papers first, then the most relevant rest.
    papers = [p for p in papers if p.id in supporting] + [p for p in papers if p.id not in supporting]
    papers = papers[:40]
    b = project.brief
    listing = "\n".join(
        f"[{n}] {p.title} ({p.year}). {p.notes['contribution']} Methods: {', '.join(p.notes['methods'][:4])}. "
        f"Data: {', '.join(p.notes['datasets'][:3])}. Limitations: {'; '.join(p.notes['limitations'][:2])}"
        for n, p in enumerate(papers)
    )
    text = (
        f"{brief_context(b)}\nData available: {b['data_resources']}\nCompute: {b['compute_resources']}\n"
        f"User expertise: {b['user_expertise']}\nConstraints: {'; '.join(b['constraints'])}\n\n"
        f"CHOSEN GAP: {gap['title']}\nQuestion: {gap['question']}\nHypothesis: {gap['hypothesis']}\n"
        f"Why open: {gap['why_open']}\nProposed approach: {gap['approach']}\nData needed: {gap['data_needed']}\n"
        f"Compute needed: {gap['compute_needed']}\nRisks: {'; '.join(gap['risks'])}\n"
        f"Closest prior work: {'; '.join(c['title'] + ' — ' + c['overlap'] for c in gap['novelty_check']['closest'])}\n\n"
        f"Common methods in the field: {', '.join(overview['common_methods'])}\n"
        f"Common datasets: {', '.join(overview['common_datasets'])}\n\nPapers:\n{listing}"
    )
    return text, papers


# ── Jobs ───────────────────────────────────────────────────────────────────


async def _finalise(plan: ResearchPlan, h: RunHandle, model: str, repair_context: list[dict]) -> ResearchPlan:
    errors = graph_errors(plan)
    if errors:
        h.phase("repairing", f"Fixing the task graph: {errors[0]}")
        repaired = await parse(
            model=model,
            instructions=REVISE_INSTRUCTIONS,
            messages=repair_context
            + [{"role": "user", "content": "Fix these structural problems:\n- " + "\n- ".join(errors)
                + "\n\nPlan:\n" + plan.model_dump_json()}],
            schema=ResearchPlan,
            reasoning_effort="low",
        )
        plan = repaired
        prune_bad_deps(plan)
        if graph_errors(plan):
            raise RuntimeError("Could not produce a valid task graph: " + "; ".join(graph_errors(plan)))
    return plan


def _cite_all(value, papers: list[Paper]):
    """Apply readable citations to every string in the plan (the model may cite anywhere)."""
    if isinstance(value, str):
        return cite(value, papers) if "[" in value else value
    if isinstance(value, list):
        return [_cite_all(v, papers) for v in value]
    if isinstance(value, dict):
        return {k: _cite_all(v, papers) for k, v in value.items()}
    return value


def _summary(plan: ResearchPlan) -> dict:
    tasks = [t for ph in plan.phases for t in ph.tasks]
    return {"phases": len(plan.phases), "tasks": len(tasks)}


async def run(project_id: str, h: RunHandle) -> dict:
    project, rows, lit = _load(project_id)
    if not project.chosen_gap or not lit:
        raise RuntimeError("Choose a research gap first")
    context, papers = _plan_context(project, rows, lit)

    h.phase("drafting", "Drafting the research plan for the chosen gap")
    plan = await parse(
        model=settings.model_reasoning,
        instructions=PLAN_INSTRUCTIONS,
        messages=[{"role": "user", "content": context}],
        schema=ResearchPlan,
        reasoning_effort="medium",
    )
    h.phase("validating", "Checking the task graph")
    plan = await _finalise(plan, h, settings.model_reasoning, [{"role": "user", "content": context}])
    data = _cite_all(plan.model_dump(), papers)
    h.counts(**_summary(plan))
    h.note("Plan ready for review")
    return {"plan": data, "gap_id": project.chosen_gap["id"], "gaps_run_id": project.chosen_gap["run_id"]}


def latest_plan_run(project_id: str) -> Run | None:
    with Session(engine) as s:
        return s.exec(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "plan", Run.status == "done")
            .order_by(Run.started_at.desc())
        ).first()


def make_revision_job(instruction: str):
    async def revise(project_id: str, h: RunHandle) -> dict:
        prev = latest_plan_run(project_id)
        if not prev:
            raise RuntimeError("No plan to revise")
        h.phase("drafting", "Revising the plan")
        # Revisions are edits to an existing plan, so the standard tier is enough.
        plan = await parse(
            model=settings.model_standard,
            instructions=REVISE_INSTRUCTIONS,
            messages=[{"role": "user", "content": f"Instruction: {instruction}\n\nCurrent plan:\n"
                       + json.dumps(prev.result["plan"])}],
            schema=ResearchPlan,
            reasoning_effort="medium",
        )
        h.phase("validating", "Checking the task graph")
        plan = await _finalise(plan, h, settings.model_standard, [])
        h.counts(**_summary(plan))
        h.note("Revision ready for review")
        return {**prev.result, "plan": plan.model_dump(), "instruction": instruction}

    return revise


def save_manual_edit(project_id: str, plan: ResearchPlan) -> Run:
    """Store a hand-edited plan as a completed plan run (keeps revision history)."""
    prev = latest_plan_run(project_id)
    if not prev:
        raise LookupError("No plan to edit")
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        run = Run(
            project_id=project_id, kind="plan", status="done", phase="done", counts=_summary(plan),
            log=[{"t": now.isoformat(), "text": "Edited by hand"}],
            result={**prev.result, "plan": plan.model_dump(), "instruction": "Edited by hand"},
            finished_at=now,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return run


# ── Approval & export ──────────────────────────────────────────────────────


def build_context(project_id: str) -> dict:
    """context.json: everything downstream agents need to know about how we got here."""
    project, rows, lit = _load(project_id)
    with Session(engine) as s:
        messages = list(
            s.exec(select(Message).where(Message.project_id == project_id).order_by(Message.created_at))
        )
        gaps_run = s.get(Run, project.chosen_gap["run_id"]) if project.chosen_gap else None
    clarify = [
        {"kind": m.kind, "role": m.role, "content": m.content, "payload": m.payload}
        for m in messages
        if m.kind in ("questions", "answers", "brief") or m.role == "user"
    ]
    return {
        "schema": "openscientist.context/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {"id": project.id, "title": project.title, "autonomous": project.autonomous,
                    "settings": project.settings},
        "brief": project.brief,
        "clarification": clarify,
        "literature": {
            "overview": lit.result["overview"] if lit else None,
            "papers": [
                {
                    "id": p.id, "title": p.title, "year": p.year, "venue": p.venue, "authors": p.authors,
                    "doi": p.doi, "url": p.url, "pdf_url": p.pdf_url, "citation_count": p.citation_count,
                    "relevance": pp.relevance, "notes": p.notes,
                }
                for pp, p in rows
            ],
        },
        "knowledge_graph": project_graph(project_id),
        "gaps": {"candidates": gaps_run.result["gaps"] if gaps_run else [], "chosen": project.chosen_gap},
    }


def approve(project_id: str) -> Project:
    prev = latest_plan_run(project_id)
    if not prev:
        raise LookupError("No plan to approve")
    plan = {"schema": "openscientist.vague_research_plan/v1", **prev.result["plan"]}
    context = build_context(project_id)
    out = EXPORT_DIR / project_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "vague_research_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project.plan = {**plan, "run_id": prev.id, "approved_at": datetime.now(timezone.utc).isoformat()}
        project.stage = "blueprint"
        s.add(project)
        s.commit()
        s.refresh(project)
        return project


def export_path(project_id: str, name: str) -> Path | None:
    path = EXPORT_DIR / project_id / name
    return path if name in EXPORT_FILES and path.is_file() else None
