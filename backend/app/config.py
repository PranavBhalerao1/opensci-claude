from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    openai_api_key: str
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
    model_reasoning: str = "gpt-6-astra"
    model_standard: str = "gpt-6-sol"
    model_bulk: str = "gpt-6-luna"

    # USD per 1M tokens: (input, cached input, output). Used for cost tracking and
    # budget enforcement; web searches are billed per call.
    model_prices: dict[str, tuple[float, float, float]] = {
        "gpt-6-astra": (10.0, 1.0, 50.0),
        "gpt-6-sol": (2.0, 0.2, 10.0),
        "gpt-6-luna": (0.10, 0.01, 0.50),
    }
    web_search_price: float = 0.01

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'openscientist.db'}"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
