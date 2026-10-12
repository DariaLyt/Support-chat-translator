"""Runtime settings loaded from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "support-chat-translator"
    database_url: str = (
        "postgresql://translator:translator@localhost:5432/translator"
    )
    redis_url: str = "redis://localhost:6379/0"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    cache_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
