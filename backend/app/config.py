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

    # Model tiers. The flagship is reserved for heavy reasoning / agentic work (gap
    # finding, planning, blueprint). Everything else uses the fast, cheap tiers:
    # standard for clarify/extraction/chat, bulk for high-volume screening.
    model_reasoning: str = "gpt-6-astra"
    model_standard: str = "gpt-6-sol"
    model_bulk: str = "gpt-6-luna"

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'openscientist.db'}"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
