import json
import re
import shutil
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from .. import beta, jobs, pipeline, refine
from ..agents import clarify
from ..agents import judge
from ..agents import blueprint as blueprint_agent
from ..agents import plan as plan_agent
from ..agents import report as report_agent
from ..auth import CurrentUser, get_current_user
from ..config import settings, tier_of
from ..db import Message, Paper, Project, ProjectPaper, Run, Secret, TaskState, Usage, engine, get_session
from ..graph import project_graph
from ..execution import orchestrator
from ..execution.sandbox import sandbox_for
from ..llm import current_project, safe_error, stream_text

router = APIRouter(prefix="/api/projects", tags=["projects"])
# Routes that start billable work (model calls or GPU jobs) also require the user to be
# under their beta spending cap; checked before the route changes any state.
billable = [Depends(beta.require_allowance)]

SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "system.md").read_text(encoding="utf-8")


class ProjectCreate(BaseModel):
    title: str | None = None
    autonomous: bool = False
    settings: dict = {}


class Answer(BaseModel):
    question_id: str
    selected: list[str] = []
    other: str | None = None


class TurnCreate(BaseModel):
    """A user turn: free text, or answers to a questions message."""

    kind: Literal["text", "answers"] = "text"
    content: str = ""
    question_message_id: str | None = None
    answers: list[Answer] = []


class BriefConfirm(BaseModel):
    depth: Literal["quick", "standard", "deep"] = "standard"
    max_papers: int | None = None


def _messages(session: Session, project_id: str) -> list[Message]:
    return list(session.exec(select(Message).where(Message.project_id == project_id).order_by(Message.created_at)))


def _get(session: Session, project_id: str, user: CurrentUser) -> Project:
    """Fetch a project, scoped to its owner. Returns 404 (never 403) for a project
    that exists but belongs to someone else, so its existence is never leaked."""
    project = session.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return project


def _no_active_review(project: Project) -> None:
    """Planning changes would pull the ground from under a scientific review in progress."""
    if (project.review or {}).get("status") in refine.ACTIVE:
        raise HTTPException(409, "A scientific review is in progress; stop it first")


def _review_idle(project_id: str) -> None:
    if jobs.is_running(project_id, "review") or jobs.is_running(project_id, "repair"):
        raise HTTPException(409, "The scientific review is working; wait for it or stop it")


@router.get("")
def list_projects(
    session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)
) -> list[Project]:
    return list(
        session.exec(select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc()))
    )


@router.post("")
def create_project(
    body: ProjectCreate, session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)
) -> Project:
    project = Project(
        user_id=user.id, autonomous=body.autonomous,
        settings={**clarify.DEFAULT_SETTINGS, "refinement": refine.default_settings(), **body.settings},
    )
    if body.title:
        project.title = body.title
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}")
def get_project(
    project_id: str, session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)
) -> dict:
    project = _get(session, project_id, user)
    return {"project": project, "messages": _messages(session, project_id)}


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str, session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)
) -> None:
    project = _get(session, project_id, user)
    if any(jobs.is_running(project_id, k) for k in ("literature", "gaps", "plan", "blueprint", "execute", "report",
                                                     "review", "repair")):
        raise HTTPException(409, "Stop the running stage before deleting")
    # Papers stay in the shared cache and usage rows stay for spend history.
    for model in (Message, ProjectPaper, TaskState, Run, Secret):
        for row in session.exec(select(model).where(model.project_id == project_id)):
            session.delete(row)
    session.delete(project)
    session.commit()
    shutil.rmtree(sandbox_for(project_id).root, ignore_errors=True)
    shutil.rmtree(plan_agent.EXPORT_DIR / project_id, ignore_errors=True)
    (sandbox_for(project_id).root.parent / f"{project_id}-research-package.zip").unlink(missing_ok=True)


@router.post("/{project_id}/brief/confirm", dependencies=billable)
async def confirm_brief(project_id: str, body: BriefConfirm, session: Session = Depends(get_session),
                        user: CurrentUser = Depends(get_current_user)) -> Project:
    project = _get(session, project_id, user)
    if not project.brief:
        raise HTTPException(409, "No research brief to confirm yet")
    preset = clarify.DEPTH_PRESETS[body.depth]
    max_papers = body.max_papers or preset["max_papers"]
    # Merge: budget, model policy and report settings chosen earlier must survive.
    project.settings = {**(project.settings or {}), **preset, "max_papers": max(10, min(max_papers, 500))}
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)
    session.commit()
    if not jobs.is_running(project_id, "literature"):
        pipeline.start_literature(project_id)
    session.refresh(project)
    return project


@router.post("/{project_id}/literature/run", dependencies=billable)
async def rerun_literature(project_id: str, session: Session = Depends(get_session),
                           user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    if project.stage == "clarify" or not project.brief:
        raise HTTPException(409, "Confirm the research brief first")
    _no_active_review(project)
    if jobs.is_running(project_id, "literature"):
        raise HTTPException(409, "Literature review already running")
    return pipeline.start_literature(project_id)


@router.get("/{project_id}/literature")
def get_literature(project_id: str, session: Session = Depends(get_session),
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "literature").order_by(Run.started_at.desc())
    ).first()
    rows = session.exec(
        select(ProjectPaper, Paper)
        .join(Paper, Paper.id == ProjectPaper.paper_id)
        .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
        .order_by(ProjectPaper.relevance.desc(), ProjectPaper.score.desc())
    ).all()
    papers = [
        {
            **p.model_dump(exclude={"norm_title", "references", "updated_at"}),
            "relevance": pp.relevance,
            "reason": pp.reason,
            "origin": pp.origin,
        }
        for pp, p in rows
    ]
    return {"run": run, "papers": papers}


class GapsRerun(BaseModel):
    feedback: str | None = None


class GapSelect(BaseModel):
    gap_id: str


@router.get("/{project_id}/gaps")
def get_gaps(project_id: str, session: Session = Depends(get_session),
            user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "gaps").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/gaps/run", dependencies=billable)
async def rerun_gaps(project_id: str, body: GapsRerun, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> Run:
    _no_active_review(_get(session, project_id, user))
    lit_done = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "literature", Run.status == "done")
    ).first()
    if not lit_done or jobs.is_running(project_id, "literature"):
        raise HTTPException(409, "Finish the literature review first")
    if jobs.is_running(project_id, "gaps"):
        raise HTTPException(409, "Gap analysis already running")
    return pipeline.start_gaps(project_id, (body.feedback or "").strip() or None)


@router.post("/{project_id}/gaps/select", dependencies=billable)
async def select_gap(project_id: str, body: GapSelect, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> Project:
    _no_active_review(_get(session, project_id, user))
    if jobs.is_running(project_id, "gaps"):
        raise HTTPException(409, "Gap analysis still running")
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "A plan is being drafted; wait for it to finish before switching gaps")
    try:
        return pipeline.choose_gap(project_id, body.gap_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


class PlanRevise(BaseModel):
    instruction: str


class PlanEdit(BaseModel):
    plan: dict


@router.get("/{project_id}/plan")
def get_plan(project_id: str, session: Session = Depends(get_session),
            user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "plan").order_by(Run.started_at.desc())
    ).first()
    revisions = len(session.exec(
        select(Run.id).where(Run.project_id == project_id, Run.kind == "plan", Run.status == "done")
    ).all())
    return {"run": run, "project": project, "revisions": revisions}


@router.post("/{project_id}/plan/run", dependencies=billable)
async def rerun_plan(project_id: str, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    if not project.chosen_gap:
        raise HTTPException(409, "Choose a research gap first")
    _no_active_review(project)
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "Plan already being drafted")
    return pipeline.start_plan(project_id)


@router.post("/{project_id}/plan/revise", dependencies=billable)
async def revise_plan(project_id: str, body: PlanRevise, session: Session = Depends(get_session),
                      user: CurrentUser = Depends(get_current_user)) -> dict:
    _no_active_review(_get(session, project_id, user))
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(400, "Empty instruction")
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "Plan already being revised")
    if not plan_agent.latest_plan_run(project_id):
        raise HTTPException(409, "No plan to revise yet")
    msg = Message(project_id=project_id, role="user", content=instruction)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    run = pipeline.start_plan(project_id, instruction)
    return {"message": msg, "run": run}


@router.put("/{project_id}/plan")
def edit_plan(project_id: str, body: PlanEdit, session: Session = Depends(get_session),
             user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    _no_active_review(project)
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "Plan is being revised")
    plan, errors = plan_agent.parse_plan(body.plan)
    if errors:
        raise HTTPException(422, {"errors": errors})
    run = plan_agent.save_manual_edit(project_id, plan)
    project.plan = None
    project.stage = "plan"
    session.add(project)
    session.commit()
    return run


@router.post("/{project_id}/plan/approve", dependencies=billable)
async def approve_plan(project_id: str, session: Session = Depends(get_session),
                       user: CurrentUser = Depends(get_current_user)) -> Project:
    _no_active_review(_get(session, project_id, user))
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "Plan is being revised")
    if jobs.is_running(project_id, "blueprint"):
        raise HTTPException(409, "A blueprint is being compiled")
    try:
        return pipeline.approve_plan(project_id)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc


class BlueprintRevise(BaseModel):
    instruction: str


@router.get("/{project_id}/blueprint")
def get_blueprint(project_id: str, session: Session = Depends(get_session),
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "blueprint").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/blueprint/run", dependencies=billable)
async def rerun_blueprint(project_id: str, session: Session = Depends(get_session),
                          user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    if not project.plan:
        raise HTTPException(409, "Approve the research plan first")
    _no_active_review(project)
    if jobs.is_running(project_id, "blueprint"):
        raise HTTPException(409, "Blueprint already being compiled")
    return pipeline.start_blueprint(project_id)


@router.post("/{project_id}/blueprint/revise", dependencies=billable)
async def revise_blueprint(project_id: str, body: BlueprintRevise, session: Session = Depends(get_session),
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    _no_active_review(_get(session, project_id, user))
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(400, "Empty instruction")
    if jobs.is_running(project_id, "blueprint"):
        raise HTTPException(409, "Blueprint already being revised")
    if not blueprint_agent.latest_run(project_id):
        raise HTTPException(409, "No blueprint to revise yet")
    msg = Message(project_id=project_id, role="user", content=instruction)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return {"message": msg, "run": pipeline.start_blueprint(project_id, instruction)}


@router.post("/{project_id}/blueprint/approve")
def approve_blueprint(project_id: str, session: Session = Depends(get_session),
                      user: CurrentUser = Depends(get_current_user)) -> Project:
    _no_active_review(_get(session, project_id, user))
    if jobs.is_running(project_id, "blueprint"):
        raise HTTPException(409, "Blueprint is being revised")
    try:
        return blueprint_agent.approve(project_id)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc


class ExecutionStart(BaseModel):
    budget_usd: float | None = None
    model_policy: Literal["default", "economy", "minimal"] | None = None


class TaskAction(BaseModel):
    note: str | None = None


def _apply_exec_settings(session: Session, project: Project, body: ExecutionStart) -> None:
    cfg = dict(project.settings or {})
    if body.budget_usd is not None:
        cfg["budget"] = {**(cfg.get("budget") or {}), "llm_usd": max(0.05, min(body.budget_usd, 500.0))}
    if body.model_policy:
        cfg["model_policy"] = body.model_policy
    project.settings = cfg
    session.add(project)
    session.commit()


@router.get("/{project_id}/execution")
def get_execution(project_id: str, session: Session = Depends(get_session),
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "execute").order_by(Run.started_at.desc())
    ).first()
    tasks: list[TaskState] = []
    if project.blueprint:
        order = {t["id"]: i for i, t in enumerate(
            session.get(Run, project.blueprint["run_id"]).result["master_plan"]["tasks"])}
        tasks = sorted(
            session.exec(select(TaskState).where(TaskState.blueprint_run_id == project.blueprint["run_id"])),
            key=lambda st: order.get(st.task_id, 999),
        )
    ctl = orchestrator.control(project_id)
    cfg = project.settings or {}
    return {
        "run": run,
        "project": project,
        "tasks": tasks,
        "spent": round(orchestrator.spent(project_id), 4),
        "budget": ((cfg.get("budget") or {}).get("llm_usd", 15.0)),
        "model_policy": cfg.get("model_policy", "default"),
        "paused": ctl.reason if ctl else None,
        "live": jobs.is_running(project_id, "execute"),
    }


@router.post("/{project_id}/execution/start", dependencies=billable)
async def start_execution(project_id: str, body: ExecutionStart, session: Session = Depends(get_session),
                          user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    if not project.blueprint:
        raise HTTPException(409, "Approve the blueprint first")
    if jobs.is_running(project_id, "execute"):
        raise HTTPException(409, "Execution already running")
    _review_idle(project_id)
    _apply_exec_settings(session, project, body)
    return pipeline.start_execution(project_id)


@router.post("/{project_id}/execution/pause")
def pause_execution(project_id: str, session: Session = Depends(get_session),
                    user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    ctl = orchestrator.control(project_id)
    if not ctl:
        raise HTTPException(409, "Execution is not running")
    ctl.pause("paused by you")
    return {"paused": ctl.reason}


@router.post("/{project_id}/execution/resume", dependencies=billable)
async def resume_execution(project_id: str, body: ExecutionStart, session: Session = Depends(get_session),
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    _review_idle(project_id)
    _apply_exec_settings(session, project, body)
    ctl = orchestrator.control(project_id)
    if ctl:
        ctl.resume()
        return {"resumed": True}
    if not project.blueprint:
        raise HTTPException(409, "Approve the blueprint first")
    pipeline.start_execution(project_id)  # restart after a finish, failure or server restart
    return {"resumed": True, "restarted": True}


@router.post("/{project_id}/execution/cancel")
def cancel_execution(project_id: str, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    ctl = orchestrator.control(project_id)
    if not ctl:
        raise HTTPException(409, "Execution is not running")
    ctl.cancelled = True
    ctl.resume()  # wake the scheduler so it can stop
    return {"cancelled": True}


@router.post("/{project_id}/execution/tasks/{task_id}/{action}")
def task_action(project_id: str, task_id: str, action: Literal["complete", "skip"], body: TaskAction,
                session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)) -> TaskState:
    _get(session, project_id, user)
    try:
        return orchestrator.set_task_status(project_id, task_id, "done" if action == "complete" else "skipped",
                                            (body.note or "").strip() or None)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class SecretIn(BaseModel):
    name: str
    value: str


@router.get("/{project_id}/secrets")
def list_secrets(project_id: str, session: Session = Depends(get_session),
                 user: CurrentUser = Depends(get_current_user)) -> list[str]:
    _get(session, project_id, user)
    return [r.name for r in session.exec(select(Secret).where(Secret.project_id == project_id))]


@router.post("/{project_id}/secrets")
def add_secret(project_id: str, body: SecretIn, session: Session = Depends(get_session),
               user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    name = body.name.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9_]{1,63}$", name) or not body.value.strip():
        raise HTTPException(400, "Invalid credential name or empty value")
    requeued = orchestrator.provide_secret(project_id, name, body.value.strip())
    return {"name": name, "requeued_tasks": requeued}


@router.get("/{project_id}/report")
def get_report(project_id: str, session: Session = Depends(get_session),
               user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "report").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/report/run", dependencies=billable)
async def run_report(project_id: str, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> Run:
    project = _get(session, project_id, user)
    if project.stage not in ("executed", "complete", "reporting", "reviewing"):
        raise HTTPException(409, "Execute the blueprint first")
    if jobs.is_running(project_id, "execute") or jobs.is_running(project_id, "report"):
        raise HTTPException(409, "A run is in progress")
    _review_idle(project_id)
    return pipeline.start_report(project_id)


REVIEW_FILES = {"mistakes.json": "application/json", "repair_plan.json": "application/json",
                "plan_revision.json": "application/json", "blueprint_delta.json": "application/json",
                "bundle.md": "text/markdown", "paper.tex": "text/plain", "paper.pdf": "application/pdf"}
REVIEW_SUMMARIES = {"HISTORY.md": "text/markdown", "REVIEW.md": "text/markdown"}


@router.get("/{project_id}/review")
def get_review(project_id: str, session: Session = Depends(get_session),
               user: CurrentUser = Depends(get_current_user)) -> dict:
    """Scientific review state (effective status, iterations, issue tracks), the latest review run,
    and the loop's log: every review and repair step of the current session, oldest first."""
    project = _get(session, project_id, user)
    view = refine.view(project_id)
    runs = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind.in_(("review", "repair")))
        .order_by(Run.started_at.desc()).limit(40)
    ).all()
    since = view.get("started_at")
    log = [{"t": line.get("t"), "text": line.get("text", ""), "kind": r.kind}
           for r in reversed(runs) if not since or r.started_at.isoformat() >= since[:19]
           for line in (r.log or [])][-400:]
    return {"review": view, "run": runs[0] if runs else None, "log": log, "project": project,
            "enabled": refine.config(project)["enabled"]}


@router.get("/{project_id}/review/file")
def get_review_file(project_id: str, name: str, iteration: int | None = None, session: Session = Depends(get_session),
                    user: CurrentUser = Depends(get_current_user)) -> FileResponse:
    _get(session, project_id, user)
    if iteration is None and name in REVIEW_SUMMARIES:
        path, media = judge.review_dir(project_id) / name, REVIEW_SUMMARIES[name]
    elif iteration is not None and name in REVIEW_FILES:
        path, media = judge.review_dir(project_id, iteration) / name, REVIEW_FILES[name]
    else:
        raise HTTPException(404, "No such review file")
    if not path.is_file():
        raise HTTPException(404, "No such review file")
    return FileResponse(path, media_type=media, filename=name, content_disposition_type="inline")


@router.post("/{project_id}/review/start", dependencies=billable)
async def start_review(project_id: str, session: Session = Depends(get_session),
                       user: CurrentUser = Depends(get_current_user)) -> dict:
    """Opt the project in and review its current paper (a new review session)."""
    _get(session, project_id, user)
    if any(jobs.is_running(project_id, k) for k in ("execute", "report", "review", "repair")):
        raise HTTPException(409, "A run is in progress")
    try:
        run = refine.start(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run": run, "review": refine.view(project_id)}


@router.post("/{project_id}/review/resume", dependencies=billable)
async def resume_review(project_id: str, session: Session = Depends(get_session),
                        user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    try:
        step = refine.resume(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"resumed": step, "review": refine.view(project_id)}


@router.post("/{project_id}/review/stop")
async def stop_review(project_id: str, session: Session = Depends(get_session),
                      user: CurrentUser = Depends(get_current_user)) -> dict:
    project = _get(session, project_id, user)
    if (project.review or {}).get("status") not in (*refine.ACTIVE, "review_failed"):
        raise HTTPException(409, "No scientific review in progress")
    refine.stop(project_id)
    return {"review": refine.view(project_id)}


@router.get("/{project_id}/package")
def download_package(project_id: str, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(get_current_user)) -> FileResponse:
    _get(session, project_id, user)
    from_thread.run(sandbox_for(project_id).pull)
    path = report_agent.package(project_id)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/{project_id}/runs/{kind}/cancel")
def cancel_stage(project_id: str, kind: Literal["literature", "gaps", "plan", "blueprint", "report", "review", "repair"],
                 session: Session = Depends(get_session), user: CurrentUser = Depends(get_current_user)) -> dict:
    """Stop a running planning or report stage (execution has its own pause/cancel)."""
    _get(session, project_id, user)
    if not jobs.cancel(project_id, kind):
        raise HTTPException(409, f"No {kind} run in progress")
    return {"cancelled": kind}


class ChangeRequest(BaseModel):
    feedback: str


@router.post("/{project_id}/execution/changes/{task_id}", dependencies=billable)
async def request_task_changes(project_id: str, task_id: str, body: ChangeRequest,
                               session: Session = Depends(get_session),
                               user: CurrentUser = Depends(get_current_user)) -> dict:
    """Reviewer feedback on a finished task: re-run it (and its dependents) with the change."""
    _get(session, project_id, user)
    if not body.feedback.strip():
        raise HTTPException(400, "Describe the change")
    _review_idle(project_id)
    try:
        rerun = orchestrator.request_changes(project_id, task_id, body.feedback.strip())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not jobs.is_running(project_id, "execute"):
        pipeline.start_execution(project_id)
    return {"rerun": rerun}


@router.get("/{project_id}/workspace/files")
def workspace_files(project_id: str, session: Session = Depends(get_session),
                    user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    _get(session, project_id, user)
    from_thread.run(sandbox_for(project_id).pull)  # files still being written by remote processes
    root = sandbox_for(project_id).root
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            out.append({"path": str(rel), "size": p.stat().st_size})
        if len(out) >= 1000:
            break
    return out


@router.get("/{project_id}/workspace/file")
def workspace_file(project_id: str, path: str, session: Session = Depends(get_session),
                   user: CurrentUser = Depends(get_current_user)) -> FileResponse:
    _get(session, project_id, user)
    sb = sandbox_for(project_id)
    from_thread.run(sb.pull)
    try:
        p = sb.path(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    rel = p.relative_to(sb.root)
    if not p.is_file() or any(part.startswith(".") for part in rel.parts):
        raise HTTPException(404, "No such file")
    return FileResponse(p, filename=p.name, content_disposition_type="inline")


@router.get("/{project_id}/files/{name}")
def download_file(project_id: str, name: str, session: Session = Depends(get_session),
                  user: CurrentUser = Depends(get_current_user)) -> FileResponse:
    _get(session, project_id, user)
    path = plan_agent.export_path(project_id, name)
    if not path:
        raise HTTPException(404, "File not exported yet")
    return FileResponse(path, media_type="application/json", filename=name)


@router.get("/{project_id}/usage")
def get_usage(project_id: str, session: Session = Depends(get_session),
              user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    rows = session.exec(select(Usage).where(Usage.project_id == project_id)).all()
    # Grouped by tier, not by model id: spend is the user's business, the model behind a tier is not.
    by_tier: dict[str, float] = {}
    for u in rows:
        tier = tier_of(u.model)
        by_tier[tier] = by_tier.get(tier, 0.0) + u.cost
    from ..execution import colab_runner

    return {"total": round(sum(by_tier.values()), 4), "by_tier": by_tier, "calls": len(rows),
            "gpu": {"spent": round(colab_runner.gpu_spent(project_id), 4), "budget": colab_runner.gpu_budget(project_id)}}


@router.get("/{project_id}/graph")
def get_graph(project_id: str, session: Session = Depends(get_session),
              user: CurrentUser = Depends(get_current_user)) -> dict:
    _get(session, project_id, user)
    return project_graph(project_id)


@router.post("/{project_id}/messages", dependencies=billable)
def post_turn(project_id: str, body: TurnCreate, session: Session = Depends(get_session),
              user: CurrentUser = Depends(get_current_user)):
    project = _get(session, project_id, user)

    if body.kind == "answers":
        q_msg = session.get(Message, body.question_message_id or "")
        if not q_msg or q_msg.project_id != project_id or q_msg.kind != "questions":
            raise HTTPException(400, "Unknown questions message")
        if any(m.kind == "answers" and (m.payload or {}).get("question_message_id") == q_msg.id
               for m in _messages(session, project_id)):
            raise HTTPException(409, "These questions were already answered")
        questions = q_msg.payload["questions"]
        answers = clarify.validate_answers(questions, [a.model_dump() for a in body.answers])
        user_msg = Message(
            project_id=project_id,
            role="user",
            kind="answers",
            content=clarify.answers_text(questions, answers, auto=False),
            payload={"question_message_id": q_msg.id, "answers": answers, "auto": False},
        )
    else:
        if not body.content.strip():
            raise HTTPException(400, "Empty message")
        user_msg = Message(project_id=project_id, role="user", content=body.content)
        if project.title == "Untitled research":
            project.title = body.content.strip().splitlines()[0][:80]

    project.updated_at = datetime.now(timezone.utc)
    session.add(user_msg)
    session.add(project)
    session.commit()
    session.refresh(user_msg)
    user_data = user_msg.model_dump(mode="json")
    stage = project.stage

    async def events() -> AsyncIterator[dict]:
        current_project.set(project_id)
        yield {"event": "message", "data": json.dumps(user_data)}
        try:
            if stage == "clarify":
                async for ev in clarify.run(project_id):
                    yield ev
            else:
                async for ev in _chat(project_id):
                    yield ev
        except Exception as exc:  # surface to the UI instead of dropping the stream
            yield {"event": "error", "data": json.dumps({"message": safe_error(exc)})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(events())


async def _chat(project_id: str) -> AsyncIterator[dict]:
    """Plain streamed chat, used for stages that are not built yet."""
    with Session(engine) as s:
        history = [{"role": m.role, "content": m.content} for m in _messages(s, project_id)]
    chunks: list[str] = []
    async for delta in stream_text(model=settings.model_standard, instructions=SYSTEM_PROMPT, messages=history):
        chunks.append(delta)
        yield {"event": "delta", "data": json.dumps({"text": delta})}
    with Session(engine) as s:
        reply = Message(project_id=project_id, role="assistant", content="".join(chunks))
        s.add(reply)
        s.commit()
        s.refresh(reply)
        yield {"event": "message", "data": reply.model_dump_json()}
