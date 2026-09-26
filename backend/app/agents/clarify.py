"""Stage 1 · Clarify.

Turns a vague prompt into a `research_brief`. The model asks at most MAX_ROUNDS
batches of multiple-choice questions, then writes the brief. In autonomous mode a
proxy call answers the questions on the user's behalf and the brief is confirmed
automatically.
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import jobs
from ..config import settings
from ..db import Message, Project, engine
from ..llm import parse

MAX_ROUNDS = 2
NOT_SURE = "Not sure — decide for me"

DEPTH_PRESETS: dict[str, dict] = {
    "quick": {"depth": "quick", "max_papers": 30, "citation_hops": 0},
    "standard": {"depth": "standard", "max_papers": 100, "citation_hops": 0},
    "deep": {"depth": "deep", "max_papers": 300, "citation_hops": 1},
}
DEFAULT_SETTINGS = DEPTH_PRESETS["standard"]


# ── Schemas (strict structured outputs: every field required) ──────────────


class Option(BaseModel):
    label: str = Field(description="Short choice, 2-8 words")
    detail: str = Field(description="One plain-language sentence explaining the choice")


class Question(BaseModel):
    id: str = Field(description="Stable slug, e.g. 'data_access'")
    question: str
    why: str = Field(description="One sentence: why this matters for the research")
    options: list[Option] = Field(description="3-5 mutually distinct options")
    multi: bool = Field(description="True if several options can be chosen together")


class KeyConcept(BaseModel):
    term: str
    definition: str = Field(description="Plain-language definition, one sentence")


class ResearchBrief(BaseModel):
    title: str = Field(description="Concise project title, max 8 words")
    core_question: str = Field(description="The sharpened research question, one sentence")
    summary: str = Field(description="2-3 plain-language sentences on what will be investigated and why")
    domain: str
    subfields: list[str]
    key_concepts: list[KeyConcept]
    scope_in: list[str] = Field(description="What the investigation covers")
    scope_out: list[str] = Field(description="What it explicitly excludes")
    result_type: Literal["empirical", "computational", "theoretical", "benchmark", "review"]
    data_resources: str = Field(description="Data the user has or public data we will rely on")
    compute_resources: str
    user_expertise: str
    constraints: list[str]
    search_keywords: list[str] = Field(description="8-15 literature search phrases, incl. synonyms")
    assumptions: list[str] = Field(description="Anything decided without explicit user input")


class ClarifyTurn(BaseModel):
    action: Literal["ask", "brief"]
    message: str = Field(description="Short lead-in shown to the user, 1-3 sentences, markdown ok")
    questions: list[Question] = Field(description="3-5 questions when action=ask, else empty")
    brief: ResearchBrief | None = Field(description="Required when action=brief, else null")


class BriefTurn(BaseModel):
    message: str
    brief: ResearchBrief


class AutoAnswer(BaseModel):
    question_id: str
    selected: list[str] = Field(description="Exact option labels chosen")
    other: str | None = Field(description="Free-text answer if no option fits, else null")
    rationale: str = Field(description="One sentence on why this choice")


class AutoAnswers(BaseModel):
    answers: list[AutoAnswer]


# ── Prompts ────────────────────────────────────────────────────────────────

CLARIFY_INSTRUCTIONS = """\
You are the Planning Agent of OpenScientist, which lets anyone (no PhD needed) run
real scientific investigations. You are in the CLARIFY stage: turn the user's vague
direction into a precise research brief.

What OpenScientist can execute: computational and data-driven research — analysing
public datasets, simulations, ML training/evaluation, statistical studies, literature
synthesis. It cannot run wet-lab or human-subject experiments; if the user's idea
needs one, steer toward a computational or secondary-data version and say so.

Rules for asking:
- Ask only what materially changes the research: the precise phenomenon, the
  population/system, what data exists or is accessible, compute budget, the kind of
  result wanted, and constraints. Do not ask what you can reasonably infer.
- 3-5 questions per round, each with 3-5 concrete options written for a smart
  non-expert. Explain jargon inside the option detail.
- Never include a "not sure" option; the interface adds one automatically. When the
  user picks "{not_sure}", make the most sensible choice yourself and record it in
  `assumptions`.
- Do not invent citations or specific paper results.

Return action="brief" as soon as you have enough to write a sharp, testable,
feasible research question. Rounds of questions asked so far: {rounds} of max {max_rounds}.
If the user asks to change an existing brief, return an updated brief.
"""

FORCE_BRIEF = "\nYou have used every question round. Write the brief now, filling gaps with sensible assumptions."

AUTO_INSTRUCTIONS = f"""\
The user chose AUTONOMOUS mode: you answer the Planning Agent's clarifying questions
on their behalf. Stay faithful to everything the user actually said. Otherwise pick
answers that make the investigation feasible for a small team (public data, a
laptop plus a modest cloud GPU budget) while still aiming at a novel, publishable
result. Prefer producing new evidence — computational experiments, re-analysis of
public datasets, meta-analysis — over a purely narrative literature review. Use exact option labels in `selected`; use `other` only if no option fits.
Never pick "{NOT_SURE}".
"""


# ── Transcript ─────────────────────────────────────────────────────────────


def _transcript(messages: list[Message]) -> list[dict]:
    """Messages as Responses API input. Structured kinds use their text rendering."""
    return [{"role": m.role, "content": m.content} for m in messages if m.content]


def questions_text(turn_message: str, questions: list[Question]) -> str:
    lines = [turn_message, ""]
    for i, q in enumerate(questions, 1):
        opts = "; ".join(o.label for o in q.options)
        lines.append(f"{i}. [{q.id}] {q.question} Options: {opts}{' (multi-select)' if q.multi else ''}")
    return "\n".join(lines)


def answers_text(questions: list[dict], answers: list[dict], auto: bool) -> str:
    by_id = {q["id"]: q for q in questions}
    head = "Answers chosen automatically on my behalf (autonomous mode):" if auto else "My answers:"
    lines = [head]
    for a in answers:
        q = by_id.get(a["question_id"], {"question": a["question_id"]})
        parts = list(a.get("selected") or [])
        if a.get("other"):
            parts.append(a["other"])
        lines.append(f"- {q['question']} → {'; '.join(parts) or '(skipped)'}")
    return "\n".join(lines)


def brief_text(message: str, brief: ResearchBrief) -> str:
    return f"{message}\n\nResearch brief:\n{brief.model_dump_json(indent=1)}"


# ── Stage runner ───────────────────────────────────────────────────────────


def _event(name: str, data) -> dict:
    return {"event": name, "data": json.dumps(data, default=str)}


def _save(session: Session, msg: Message) -> dict:
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg.model_dump(mode="json")


def _touch(project: Project) -> None:
    project.updated_at = datetime.now(timezone.utc)


def validate_answers(questions: list[dict], answers: list[dict]) -> list[dict]:
    """Keep only answers to known questions and options that actually exist."""
    by_id = {q["id"]: q for q in questions}
    clean = []
    for a in answers:
        q = by_id.get(a.get("question_id"))
        if not q:
            continue
        labels = {o["label"] for o in q["options"]} | {NOT_SURE}
        selected = [s for s in a.get("selected") or [] if s in labels]
        if not q["multi"]:
            selected = selected[:1]
        other = (a.get("other") or "").strip() or None
        clean.append({**a, "selected": selected, "other": other})
    return clean


async def run(project_id: str) -> AsyncIterator[dict]:
    """Advance the clarify stage until it needs the user again (or finishes)."""
    while True:
        with Session(engine) as s:
            project = s.get(Project, project_id)
            messages = list(
                s.exec(select(Message).where(Message.project_id == project_id).order_by(Message.created_at))
            )
        rounds = sum(1 for m in messages if m.kind == "questions")
        history = _transcript(messages)
        force = rounds >= MAX_ROUNDS

        status = "Writing your research brief" if force else "Reading your answers" if rounds else "Thinking about what to ask"
        yield _event("status", {"text": status})
        instructions = CLARIFY_INSTRUCTIONS.format(rounds=rounds, max_rounds=MAX_ROUNDS, not_sure=NOT_SURE)
        if force:
            out = await parse(
                model=settings.model_standard,
                instructions=instructions + FORCE_BRIEF,
                messages=history,
                schema=BriefTurn,
            )
            turn = ClarifyTurn(action="brief", message=out.message, questions=[], brief=out.brief)
        else:
            turn = await parse(
                model=settings.model_standard, instructions=instructions, messages=history, schema=ClarifyTurn
            )

        if turn.action == "ask" and turn.questions:
            with Session(engine) as s:
                q_msg = Message(
                    project_id=project_id,
                    role="assistant",
                    kind="questions",
                    content=questions_text(turn.message, turn.questions),
                    payload={
                        "message": turn.message,
                        "questions": [q.model_dump() for q in turn.questions],
                        "round": rounds + 1,
                    },
                )
                q_data = _save(s, q_msg)
            yield _event("message", q_data)

            if not project.autonomous:
                return

            yield _event("status", {"text": "Answering on your behalf"})
            auto = await parse(
                model=settings.model_standard,
                instructions=AUTO_INSTRUCTIONS,
                messages=history + [{"role": "user", "content": "Questions to answer:\n" + q_data["content"]}],
                schema=AutoAnswers,
                reasoning_effort="low",
            )
            questions = q_data["payload"]["questions"]
            answers = validate_answers(questions, [a.model_dump() for a in auto.answers])
            with Session(engine) as s:
                a_data = _save(
                    s,
                    Message(
                        project_id=project_id,
                        role="user",
                        kind="answers",
                        content=answers_text(questions, answers, auto=True),
                        payload={"question_message_id": q_data["id"], "answers": answers, "auto": True},
                    ),
                )
            yield _event("message", a_data)
            continue

        # Brief (also the fallback if the model chose "ask" with no questions).
        brief = turn.brief
        if brief is None:
            raise RuntimeError("Clarify step returned neither questions nor a brief")
        with Session(engine) as s:
            b_data = _save(
                s,
                Message(
                    project_id=project_id,
                    role="assistant",
                    kind="brief",
                    content=brief_text(turn.message, brief),
                    payload={"message": turn.message, "brief": brief.model_dump()},
                ),
            )
            project = s.get(Project, project_id)
            project.brief = brief.model_dump()
            project.title = brief.title
            project.settings = {**DEFAULT_SETTINGS, **(project.settings or {})}
            if project.autonomous:
                project.stage = "literature"
            _touch(project)
            s.add(project)
            s.commit()
            s.refresh(project)
            p_data = project.model_dump(mode="json")
        yield _event("message", b_data)
        yield _event("project", p_data)
        if p_data["stage"] == "literature" and not jobs.is_running(project_id, "literature"):
            from .. import pipeline  # local import: pipeline imports this module's siblings

            pipeline.start_literature(project_id)
        return
