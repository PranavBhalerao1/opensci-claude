from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Uuid, inspect, text
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
    # SQLModel's default table name is the bare lowercased class name ("project"),
    # which does not match supabase/migrations (snake_case, pluralised). Every
    # table below sets __tablename__ explicitly so the ORM and the RLS-protected
    # Postgres schema refer to the same tables.
    __tablename__ = "projects"

    id: str = Field(default_factory=_id, primary_key=True)
    # The Supabase auth.users.id that owns this project. Set only from a verified bearer
    # token (see app/auth.py); the API never trusts a user_id supplied by the client.
    # Nullable at the ORM level so the offline SQLite test suite can create projects
    # without a real Supabase user; the Postgres migration enforces NOT NULL for real data.
    user_id: str | None = Field(default=None, sa_column=Column(Uuid(as_uuid=False), index=True))
    title: str = "Untitled research"
    # clarify -> literature -> gaps -> plan -> blueprint -> ready -> executing -> executed
    #   -> reporting -> [reviewing ->] complete (refinement may loop back through execution)
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
    # Scientific review and refinement state (see refine.py); None = never reviewed
    review: dict | None = Field(default=None, sa_column=Column(NullableJSON))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
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

    __tablename__ = "papers"

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

    __tablename__ = "project_papers"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    paper_id: str = Field(foreign_key="papers.id", index=True)
    origin: str = "search"  # search | citation
    score: float = 0.0  # retrieval score before screening
    relevance: int | None = None  # 0-3 from screening
    reason: str | None = None
    included: bool = False


class SearchCache(SQLModel, table=True):
    """Recent search results, so repeat queries in a field skip the API."""

    __tablename__ = "search_cache"

    key: str = Field(primary_key=True)  # source:normalised query:limit
    paper_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    fetched_at: datetime = Field(default_factory=_now)


class Run(SQLModel, table=True):
    """A long-running stage job; the UI polls it for progress."""

    __tablename__ = "runs"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    kind: str  # literature | gaps | plan | blueprint | execute | report | review | repair
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

    __tablename__ = "task_states"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
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

    __tablename__ = "secrets"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    name: str
    value: str
    created_at: datetime = Field(default_factory=_now)


class GpuUsage(SQLModel, table=True):
    """One cloud GPU job's metered runtime and estimated cost."""

    __tablename__ = "gpu_usage"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    # Owner at write time, so spend stays attributable after the project is deleted.
    user_id: str | None = Field(default=None, sa_column=Column(Uuid(as_uuid=False), index=True))
    run_id: str | None = None
    gpu: str
    job: str
    seconds: float = 0.0
    cost: float = 0.0
    created_at: datetime = Field(default_factory=_now)


class Usage(SQLModel, table=True):
    """One LLM call's token usage and estimated cost."""

    __tablename__ = "usage"

    id: str = Field(default_factory=_id, primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    # Owner at write time, so spend stays attributable after the project is deleted.
    user_id: str | None = Field(default=None, sa_column=Column(Uuid(as_uuid=False), index=True))
    run_id: str | None = Field(default=None, index=True)
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0
    cost: float = 0.0
    created_at: datetime = Field(default_factory=_now)


class BetaUser(SQLModel, table=True):
    """Private-beta access for one Supabase user (see app/beta.py). Managed by hand in
    the Supabase table editor: approved false → true, cap_usd in USD (None = unlimited)."""

    __tablename__ = "beta_users"

    user_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    approved: bool = False
    cap_usd: float | None = None
    created_at: datetime = Field(default_factory=_now)


class Subscription(SQLModel, table=True):
    """A paid plan, one row per Supabase user. Written only by the Stripe webhook on the
    website (frontend/src/app/api/stripe/webhook); the backend just reads it (app/beta.py)."""

    __tablename__ = "subscriptions"

    user_id: str = Field(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    plan: str  # light | intensive | ultra
    status: str  # Stripe's subscription status: active, trialing, past_due, canceled, ...
    credits_usd: float = 0.0  # compute allowance per billing period, in USD of metered cost
    period_start: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    period_end: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    updated_at: datetime = Field(default_factory=_now)


def _engine_url(url: str) -> str:
    """Normalise a raw Postgres connection string (as copied from the Supabase dashboard)
    to the psycopg3 driver SQLAlchemy needs; sqlite URLs pass through unchanged."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


DATABASE_URL = _engine_url(settings.database_url)
_is_sqlite = DATABASE_URL.startswith("sqlite:///")

if _is_sqlite:
    Path(DATABASE_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if _is_sqlite else {})


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
