"""Runtime settings loaded from the environment."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.pricing import ModelPrice


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
    # Standard OpenAI rates, USD per 1M tokens, checked October 2026.
    # Cached-input and batch rates are separate and are not used here.
    model_a_name: str = "gpt-4.1-mini"
    model_a_input_price_per_million: float = 0.40
    model_a_output_price_per_million: float = 1.60
    model_b_name: str = "gpt-4.1"
    model_b_input_price_per_million: float = 2.00
    model_b_output_price_per_million: float = 8.00

    @model_validator(mode="after")
    def models_have_distinct_names(self) -> "Settings":
        if self.model_a_name == self.model_b_name:
            raise ValueError("MODEL_A_NAME and MODEL_B_NAME must be different")
        return self

    def model_prices(self) -> dict[str, ModelPrice]:
        return {
            self.model_a_name: ModelPrice(
                name=self.model_a_name,
                input_price_per_million=self.model_a_input_price_per_million,
                output_price_per_million=self.model_a_output_price_per_million,
            ),
            self.model_b_name: ModelPrice(
                name=self.model_b_name,
                input_price_per_million=self.model_b_input_price_per_million,
                output_price_per_million=self.model_b_output_price_per_million,
            ),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
