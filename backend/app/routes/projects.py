import json
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
from ..config import settings
from ..db import Message, Paper, Project, ProjectPaper, Run, Usage, engine, get_session
from ..graph import project_graph
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
    for m in _messages(session, project_id):
        session.delete(m)
    session.delete(project)
    session.commit()


@router.post("/{project_id}/brief/confirm")
async def confirm_brief(project_id: str, body: BriefConfirm, session: Session = Depends(get_session)) -> Project:
    project = _get(session, project_id)
    if not project.brief:
        raise HTTPException(409, "No research brief to confirm yet")
    preset = clarify.DEPTH_PRESETS[body.depth]
    max_papers = body.max_papers or preset["max_papers"]
    project.settings = {**preset, "max_papers": max(10, min(max_papers, 500))}
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
