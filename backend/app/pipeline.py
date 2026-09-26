"""Stage chaining: which job starts after which, and autonomous auto-decisions.

confirm brief → literature → gaps → choose gap (autonomous: recommended) → plan
→ approve (autonomous: automatic) → done
"""

import functools
from datetime import datetime, timezone

from sqlmodel import Session, select

from . import jobs
from .agents import gaps, literature
from .agents import plan as plan_agent
from .db import Project, Run, engine


def _set_stage(project_id: str, stage: str) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project.stage = stage
        project.updated_at = datetime.now(timezone.utc)
        s.add(project)
        s.commit()


def start_literature(project_id: str) -> Run:
    _set_stage(project_id, "literature")
    return jobs.start(project_id, "literature", literature.run, then=_after_literature)


async def _after_literature(project_id: str) -> None:
    if not jobs.is_running(project_id, "gaps"):
        start_gaps(project_id)


def start_gaps(project_id: str, feedback: str | None = None) -> Run:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project.chosen_gap = None
        project.plan = None
        s.add(project)
        s.commit()
    _set_stage(project_id, "gaps")
    job = functools.partial(gaps.run, feedback=feedback)
    return jobs.start(project_id, "gaps", job, then=_after_gaps)


async def _after_gaps(project_id: str) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        autonomous = project.autonomous
    if not autonomous:
        return
    with Session(engine) as s:
        run = s.exec(
            select(Run).where(Run.project_id == project_id, Run.kind == "gaps").order_by(Run.started_at.desc())
        ).first()
    choose_gap(project_id, run.result["recommended"])


def choose_gap(project_id: str, gap_id: str) -> Project:
    project = gaps.choose(project_id, gap_id)
    start_plan(project_id)
    return project


def start_plan(project_id: str, instruction: str | None = None) -> Run:
    """Draft a plan, or revise the latest one when `instruction` is given."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
        project.plan = None  # any change invalidates a previous approval
        project.stage = "plan"
        s.add(project)
        s.commit()
    job = plan_agent.make_revision_job(instruction) if instruction else plan_agent.run
    return jobs.start(project_id, "plan", job, then=_after_plan)


async def _after_plan(project_id: str) -> None:
    with Session(engine) as s:
        autonomous = s.get(Project, project_id).autonomous
    if autonomous:
        plan_agent.approve(project_id)
