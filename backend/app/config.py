from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

SONNET_4_6 = "us.anthropic.claude-sonnet-4-6"  # Bedrock US cross-region inference profile
# OpenAI models (LLM_PROVIDER=openai): the flagship for reasoning, standard and judging; the mini
# model for high-volume screening.
GPT_FLAGSHIP = "gpt-5.5"
GPT_MINI = "gpt-5.4-mini"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Claude on Amazon Bedrock. Passed to the client explicitly: values from .env are not
    # exported to os.environ, so the AWS default credential chain would not see them.
    # Unset keys fall back to that chain (profile, instance role).
    aws_region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    bedrock_model_id: str = SONNET_4_6
    # "bedrock" (Claude on Amazon Bedrock) or "openai" (app/openai_client.py). Unset, it is
    # "openai" when OPENAI_API_KEY is set and "bedrock" otherwise.
    llm_provider: str = ""
    openai_api_key: str | None = None
    # With OpenAI, no call reasons below this effort ("low" < "medium" < "high"), and every call
    # may write at least this many output tokens (reasoning included; only used tokens are billed).
    openai_min_effort: str = "medium"
    openai_min_output_tokens: int = 32_000
    # Backs the agents' web_search tool.
    tavily_api_key: str | None = None

    semantic_scholar_api_key: str | None = None
    # OpenAlex works keyless on a small free daily budget; a key raises it.
    openalex_api_key: str | None = None

    # Supabase project used for authentication. supabase_url is required to verify
    # bearer tokens (fetches the project's JWKS); supabase_jwt_secret is only needed
    # for projects still on the legacy shared-secret (HS256) signing key.
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    # Accounts that may only watch the frontend's scripted walkthrough (comma-separated,
    # added to the built-in list in app/auth.py). The API rejects them on every route.
    walkthrough_emails: str = ""

    # Model tiers. The flagship is reserved for heavy reasoning / agentic work (gap
    # finding, planning, blueprint). Everything else uses the fast, cheap tiers:
    # standard for clarify/extraction/chat, bulk for high-volume screening.
    # Empty tiers use BEDROCK_MODEL_ID.
    model_reasoning: str = ""
    model_standard: str = ""
    model_bulk: str = ""
    # The independent scientific judge (agents/judge.py); a fresh call per review.
    model_judge: str = ""

    # Scientific review and refinement (refine.py). New projects get refinement_default;
    # projects without a "refinement" setting keep the plain pipeline. max_usd counts LLM
    # and GPU spend after refinement starts.
    refinement_default: bool = True
    refinement_max_rounds: int = 12
    refinement_max_usd: float = 60.0
    # The judge's 0-10 score a paper must reach to be approved; 10 = flawless (agents/judge.py).
    refinement_target_score: float = 10.0
    review_numeric_crosscheck: bool = True
    # Reviews by a panel: the lead judge plus specialist theory and methods referees, in parallel
    # (agents/judge.py REFEREES). Off, a review is the lead judge alone.
    review_panel: bool = True
    # Before a plan is shown for approval, a domain-expert audit checks whether its hypothesis is
    # already implied by established theory, ill-posed in some regime, or confuses a bound with a
    # threshold, and the plan is revised once if so (agents/plan.py audit_plan).
    plan_audit: bool = True
    # Attempts per execution task before it is left failed. Every retry gets a fresh model's
    # diagnosis of the failure and the exact fix to make (orchestrator._advise).
    task_max_attempts: int = 6

    # USD per 1M tokens: (input, cached input, output). Used for cost tracking (which
    # feeds credit and project-budget checks); web searches are billed per call. Bedrock regional (us.)
    # inference profiles cost 10% more than Anthropic's list price ($3 / $0.30 / $15).
    model_prices: dict[str, tuple[float, float, float]] = {
        SONNET_4_6: (3.30, 0.33, 16.50),
        # Estimates, set on the high side so credit checks never undercount.
        GPT_FLAGSHIP: (5.00, 0.50, 30.00),
        GPT_MINI: (0.75, 0.075, 4.50),
    }
    web_search_price: float = 0.01

    # Agent code always runs in E2B cloud sandboxes; explicit CUDA GPU jobs go to Google Colab.
    e2b_api_key: str | None = None
    e2b_template: str = "openscientist-cpu"

    # run_gpu_jobs always runs on Google Colab through the `colab` CLI (Linux/macOS; see
    # docs/colab-gpu.md). colab_credentials_file is the ADC authorized-user JSON from
    # `gcloud auth application-default login`; keep it outside the repo.
    colab_credentials_file: str | None = None
    colab_max_sessions: int = 1

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'openscientist.db'}"
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _default_tiers(self) -> "Settings":
        if not self.llm_provider:
            self.llm_provider = "openai" if self.openai_api_key else "bedrock"
        openai = self.llm_provider == "openai"
        for tier in ("model_reasoning", "model_standard", "model_bulk", "model_judge"):
            if not getattr(self, tier):
                default = (GPT_MINI if tier == "model_bulk" else GPT_FLAGSHIP) if openai else self.bedrock_model_id
                setattr(self, tier, default)
        return self


settings = Settings()

# The order tier_of() tries tiers in. Tiers may share a model id (they all default to
# bedrock_model_id) and a usage row records only the id, so a shared id cannot be attributed to the
# tier that spent it: the first match wins, and "standard" leads as the most-used tier. A tier
# configured with an id of its own always resolves to itself, whatever its place here.
TIER_ORDER = ("standard", "reasoning", "bulk", "judge")


def tier_of(model_id: str) -> str:
    """The tier name for a stored model id: a cost bucket, not provenance (see TIER_ORDER). What a
    user can see names the tier, never the model or provider behind it; raw ids stay in the Usage
    table and the logs, where cost accounting needs them."""
    return next((t for t in TIER_ORDER if getattr(settings, f"model_{t}") == model_id), "other")
