from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

SONNET_4_6 = "us.anthropic.claude-sonnet-4-6"  # Bedrock US cross-region inference profile


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

    # Model tiers. The flagship is reserved for heavy reasoning / agentic work (gap
    # finding, planning, blueprint). Everything else uses the fast, cheap tiers:
    # standard for clarify/extraction/chat, bulk for high-volume screening.
    # Empty tiers use BEDROCK_MODEL_ID.
    model_reasoning: str = ""
    model_standard: str = ""
    model_bulk: str = ""

    # USD per 1M tokens: (input, cached input, output). Used for cost tracking and
    # budget enforcement; web searches are billed per call. Bedrock regional (us.)
    # inference profiles cost 10% more than Anthropic's list price ($3 / $0.30 / $15).
    model_prices: dict[str, tuple[float, float, float]] = {
        SONNET_4_6: (3.30, 0.33, 16.50),
    }
    web_search_price: float = 0.01

    # Agent code always runs in E2B cloud sandboxes; explicit CUDA GPU jobs go to Modal.
    e2b_api_key: str | None = None
    e2b_template: str = "openscientist-cpu"

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'openscientist.db'}"
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _default_tiers(self) -> "Settings":
        for tier in ("model_reasoning", "model_standard", "model_bulk"):
            if not getattr(self, tier):
                setattr(self, tier, self.bedrock_model_id)
        return self


settings = Settings()
