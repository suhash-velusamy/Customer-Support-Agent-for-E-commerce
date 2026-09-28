"""Application settings loaded from environment / .env."""

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    tavily_api_key: str = ""
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'support.db'}"
    demo_customer_id: str = "CUST-001"
    # Use the LLM (via OpenRouter) for intent classification when a key is set.
    use_llm_triage: bool = True
    # "Today" for date calculations. Defaults to the seed reference date so the demo data stays coherent.
    demo_today: date | None = None

    @property
    def database_path(self) -> Path:
        path = Path(self.database_url.removeprefix("sqlite:///"))
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
