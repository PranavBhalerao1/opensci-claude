import json
import re
import shutil
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from .. import jobs, pipeline
from ..agents import clarify
from ..agents import blueprint as blueprint_agent
from ..agents import plan as plan_agent
from ..agents import report as report_agent
from ..config import settings
from ..db import Message, Paper, Project, ProjectPaper, Run, Secret, TaskState, Usage, engine, get_session
from ..graph import project_graph
from ..execution import orchestrator
from ..execution.sandbox import sandbox_for
from ..llm import current_project, stream_text

router = APIRouter(prefix="/api/projects", tags=["projects"])

SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "system.md").read_text()


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


def _get(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("")
def list_projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.updated_at.desc())))


@router.post("")
def create_project(body: ProjectCreate, session: Session = Depends(get_session)) -> Project:
    project = Project(autonomous=body.autonomous, settings={**clarify.DEFAULT_SETTINGS, **body.settings})
    if body.title:
        project.title = body.title
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
    return {"project": project, "messages": _messages(session, project_id)}


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_session)) -> None:
    project = _get(session, project_id)
    if any(jobs.is_running(project_id, k) for k in ("literature", "gaps", "plan", "blueprint", "execute", "report")):
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


@router.post("/{project_id}/brief/confirm")
async def confirm_brief(project_id: str, body: BriefConfirm, session: Session = Depends(get_session)) -> Project:
    project = _get(session, project_id)
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


@router.post("/{project_id}/literature/run")
async def rerun_literature(project_id: str, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
    if project.stage == "clarify" or not project.brief:
        raise HTTPException(409, "Confirm the research brief first")
    if jobs.is_running(project_id, "literature"):
        raise HTTPException(409, "Literature review already running")
    return pipeline.start_literature(project_id)


@router.get("/{project_id}/literature")
def get_literature(project_id: str, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
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
def get_gaps(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "gaps").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/gaps/run")
async def rerun_gaps(project_id: str, body: GapsRerun, session: Session = Depends(get_session)) -> Run:
    _get(session, project_id)
    lit_done = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "literature", Run.status == "done")
    ).first()
    if not lit_done or jobs.is_running(project_id, "literature"):
        raise HTTPException(409, "Finish the literature review first")
    if jobs.is_running(project_id, "gaps"):
        raise HTTPException(409, "Gap analysis already running")
    return pipeline.start_gaps(project_id, (body.feedback or "").strip() or None)


@router.post("/{project_id}/gaps/select")
async def select_gap(project_id: str, body: GapSelect, session: Session = Depends(get_session)) -> Project:
    _get(session, project_id)
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
def get_plan(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "plan").order_by(Run.started_at.desc())
    ).first()
    revisions = len(session.exec(
        select(Run.id).where(Run.project_id == project_id, Run.kind == "plan", Run.status == "done")
    ).all())
    return {"run": run, "project": project, "revisions": revisions}


@router.post("/{project_id}/plan/run")
async def rerun_plan(project_id: str, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
    if not project.chosen_gap:
        raise HTTPException(409, "Choose a research gap first")
    if jobs.is_running(project_id, "plan"):
        raise HTTPException(409, "Plan already being drafted")
    return pipeline.start_plan(project_id)


@router.post("/{project_id}/plan/revise")
async def revise_plan(project_id: str, body: PlanRevise, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
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
def edit_plan(project_id: str, body: PlanEdit, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
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


@router.post("/{project_id}/plan/approve")
async def approve_plan(project_id: str, session: Session = Depends(get_session)) -> Project:
    _get(session, project_id)
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
def get_blueprint(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "blueprint").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/blueprint/run")
async def rerun_blueprint(project_id: str, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
    if not project.plan:
        raise HTTPException(409, "Approve the research plan first")
    if jobs.is_running(project_id, "blueprint"):
        raise HTTPException(409, "Blueprint already being compiled")
    return pipeline.start_blueprint(project_id)


@router.post("/{project_id}/blueprint/revise")
async def revise_blueprint(project_id: str, body: BlueprintRevise, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
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
def approve_blueprint(project_id: str, session: Session = Depends(get_session)) -> Project:
    _get(session, project_id)
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
def get_execution(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
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


@router.post("/{project_id}/execution/start")
async def start_execution(project_id: str, body: ExecutionStart, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
    if not project.blueprint:
        raise HTTPException(409, "Approve the blueprint first")
    if jobs.is_running(project_id, "execute"):
        raise HTTPException(409, "Execution already running")
    _apply_exec_settings(session, project, body)
    return pipeline.start_execution(project_id)


@router.post("/{project_id}/execution/pause")
def pause_execution(project_id: str) -> dict:
    ctl = orchestrator.control(project_id)
    if not ctl:
        raise HTTPException(409, "Execution is not running")
    ctl.pause("paused by you")
    return {"paused": ctl.reason}


@router.post("/{project_id}/execution/resume")
async def resume_execution(project_id: str, body: ExecutionStart, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
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
def cancel_execution(project_id: str) -> dict:
    ctl = orchestrator.control(project_id)
    if not ctl:
        raise HTTPException(409, "Execution is not running")
    ctl.cancelled = True
    ctl.resume()  # wake the scheduler so it can stop
    return {"cancelled": True}


@router.post("/{project_id}/execution/tasks/{task_id}/{action}")
def task_action(project_id: str, task_id: str, action: Literal["complete", "skip"], body: TaskAction,
                session: Session = Depends(get_session)) -> TaskState:
    _get(session, project_id)
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
def list_secrets(project_id: str, session: Session = Depends(get_session)) -> list[str]:
    _get(session, project_id)
    return [r.name for r in session.exec(select(Secret).where(Secret.project_id == project_id))]


@router.post("/{project_id}/secrets")
def add_secret(project_id: str, body: SecretIn, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
    name = body.name.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9_]{1,63}$", name) or not body.value.strip():
        raise HTTPException(400, "Invalid credential name or empty value")
    requeued = orchestrator.provide_secret(project_id, name, body.value.strip())
    return {"name": name, "requeued_tasks": requeued}


@router.get("/{project_id}/report")
def get_report(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _get(session, project_id)
    run = session.exec(
        select(Run).where(Run.project_id == project_id, Run.kind == "report").order_by(Run.started_at.desc())
    ).first()
    return {"run": run, "project": project}


@router.post("/{project_id}/report/run")
async def run_report(project_id: str, session: Session = Depends(get_session)) -> Run:
    project = _get(session, project_id)
    if project.stage not in ("executed", "complete", "reporting"):
        raise HTTPException(409, "Execute the blueprint first")
    if jobs.is_running(project_id, "execute") or jobs.is_running(project_id, "report"):
        raise HTTPException(409, "A run is in progress")
    return pipeline.start_report(project_id)


@router.get("/{project_id}/package")
def download_package(project_id: str, session: Session = Depends(get_session)) -> FileResponse:
    _get(session, project_id)
    path = report_agent.package(project_id)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/{project_id}/runs/{kind}/cancel")
def cancel_stage(project_id: str, kind: Literal["literature", "gaps", "plan", "blueprint", "report"],
                 session: Session = Depends(get_session)) -> dict:
    """Stop a running planning or report stage (execution has its own pause/cancel)."""
    _get(session, project_id)
    if not jobs.cancel(project_id, kind):
        raise HTTPException(409, f"No {kind} run in progress")
    return {"cancelled": kind}


class ChangeRequest(BaseModel):
    feedback: str


@router.post("/{project_id}/execution/changes/{task_id}")
async def request_task_changes(project_id: str, task_id: str, body: ChangeRequest,
                               session: Session = Depends(get_session)) -> dict:
    """Reviewer feedback on a finished task: re-run it (and its dependents) with the change."""
    _get(session, project_id)
    if not body.feedback.strip():
        raise HTTPException(400, "Describe the change")
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
def workspace_files(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    _get(session, project_id)
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
def workspace_file(project_id: str, path: str, session: Session = Depends(get_session)) -> FileResponse:
    _get(session, project_id)
    sb = sandbox_for(project_id)
    try:
        p = sb.path(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    rel = p.relative_to(sb.root)
    if not p.is_file() or any(part.startswith(".") for part in rel.parts):
        raise HTTPException(404, "No such file")
    return FileResponse(p, filename=p.name, content_disposition_type="inline")


@router.get("/{project_id}/files/{name}")
def download_file(project_id: str, name: str, session: Session = Depends(get_session)) -> FileResponse:
    _get(session, project_id)
    path = plan_agent.export_path(project_id, name)
    if not path:
        raise HTTPException(404, "File not exported yet")
    return FileResponse(path, media_type="application/json", filename=name)


@router.get("/{project_id}/usage")
def get_usage(project_id: str, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
    rows = session.exec(select(Usage).where(Usage.project_id == project_id)).all()
    by_model: dict[str, float] = {}
    for u in rows:
        by_model[u.model] = by_model.get(u.model, 0.0) + u.cost
    return {"total": round(sum(by_model.values()), 4), "by_model": by_model, "calls": len(rows)}


@router.get("/{project_id}/graph")
def get_graph(project_id: str, session: Session = Depends(get_session)) -> dict:
    _get(session, project_id)
    return project_graph(project_id)


@router.post("/{project_id}/messages")
def post_turn(project_id: str, body: TurnCreate, session: Session = Depends(get_session)):
    project = _get(session, project_id)

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
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}
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
