from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Column, inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine

from .config import settings


# Stores None as SQL NULL (plain JSON stores the JSON literal null), so that
# `column.is_(None)` filters work.
NullableJSON = JSON(none_as_null=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid4().hex[:12]


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    title: str = "Untitled research"
    # clarify -> literature -> gaps -> plan -> blueprint -> ready -> executing -> executed
    #   -> reporting -> complete
    stage: str = "clarify"
    autonomous: bool = False
    settings: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # research_brief produced by the Clarify stage (see agents/clarify.py)
    brief: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    # The research gap chosen in the Gaps stage (see agents/gaps.py)
    chosen_gap: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    # The approved vague_research_plan (see agents/plan.py)
    plan: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    # Approval record for master_plan.json (see agents/blueprint.py)
    blueprint: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    role: str  # "user" | "assistant"
    # text | questions | answers | brief. Structured kinds carry their data in payload;
    # content always holds a plain-text rendering for the model transcript.
    kind: str = "text"
    content: str
    payload: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    created_at: datetime = Field(default_factory=_now)


class Paper(SQLModel, table=True):
    """Global paper cache shared by every project. Notes and references are
    question-independent, so once a paper is read it is never read again; the
    knowledge graph grows as more projects touch a field."""

    id: str = Field(default_factory=_id, primary_key=True)
    title: str
    norm_title: str = Field(index=True)
    abstract: str | None = None
    tldr: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list = Field(default_factory=list, sa_column=Column(JSON))
    citation_count: int = 0
    doi: str | None = Field(default=None, index=True)
    arxiv_id: str | None = Field(default=None, index=True)
    s2_id: str | None = Field(default=None, index=True)
    openalex_id: str | None = Field(default=None, index=True)
    url: str | None = None
    pdf_url: str | None = None
    # Structured extraction (agents/literature.py PaperNotes) and S2 reference ids.
    notes: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    references: list | None = Field(default=None, sa_column=Column(NullableJSON))
    updated_at: datetime = Field(default_factory=_now)


class ProjectPaper(SQLModel, table=True):
    """A paper considered by one project's literature review."""

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    paper_id: str = Field(foreign_key="paper.id", index=True)
    origin: str = "search"  # search | citation
    score: float = 0.0  # retrieval score before screening
    relevance: int | None = None  # 0-3 from screening
    reason: str | None = None
    included: bool = False


class SearchCache(SQLModel, table=True):
    """Recent search results, so repeat queries in a field skip the API."""

    key: str = Field(primary_key=True)  # source:normalised query:limit
    paper_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    fetched_at: datetime = Field(default_factory=_now)


class Run(SQLModel, table=True):
    """A long-running stage job; the UI polls it for progress."""

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    kind: str  # literature | gaps | plan
    status: str = "running"  # running | done | error
    phase: str = "starting"
    counts: dict = Field(default_factory=dict, sa_column=Column(JSON))
    log: list = Field(default_factory=list, sa_column=Column(JSON))
    result: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    error: str | None = None
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class TaskState(SQLModel, table=True):
    """Execution state of one blueprint task (see execution/orchestrator.py)."""

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    blueprint_run_id: str = Field(index=True)
    task_id: str
    agent: str
    # pending | running | done | failed | blocked | human | skipped | cancelled
    status: str = "pending"
    attempts: int = 0
    cost: float = 0.0
    summary: str | None = None
    artifacts: list = Field(default_factory=list, sa_column=Column(JSON))
    checks: list = Field(default_factory=list, sa_column=Column(JSON))
    issues: list = Field(default_factory=list, sa_column=Column(JSON))
    events: list = Field(default_factory=list, sa_column=Column(JSON))
    note: str | None = None  # human note, block reason, or failure reason
    feedback: str | None = None  # reviewer's requested changes for the next run of this task
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Secret(SQLModel, table=True):
    """A credential the user supplied for one project (exposed to its sandbox as an env var).
    Stored in the local database; never returned by the API after saving."""

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    name: str
    value: str
    created_at: datetime = Field(default_factory=_now)


class Usage(SQLModel, table=True):
    """One LLM call's token usage and estimated cost."""

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    run_id: str | None = Field(default=None, index=True)
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0
    cost: float = 0.0
    created_at: datetime = Field(default_factory=_now)


if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Minimal migration: add nullable columns that new model fields introduced.
    (create_all never alters existing tables.)"""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing and col.nullable:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
