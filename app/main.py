"""FastAPI application."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from app.cache import RedisTranslationCache, TranslationCache
from app.config import Settings, get_settings
from app.db import PostgresTranslationStore, TranslationRecord, TranslationStore
from app.detection import LinguaDetector, LanguageDetectorProtocol
from app.llm.base import LanguageModel
from app.llm.openai_client import OpenAICompatibleClient
from app.translate import Translation, TranslationError, translate_message


class HealthResponse(BaseModel):
    status: str


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    source_language: Literal["auto", "fi", "en"] = "auto"
    target_language: Literal["fi", "en"]
    model: str | None = None

    @field_validator("text")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text is empty")
        return stripped

    @field_validator("model")
    @classmethod
    def blank_model_means_default(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TranslateResponse(BaseModel):
    source_language: str
    target_language: str
    translation: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cached: bool


def create_app(
    settings: Settings | None = None,
    language_model: LanguageModel | None = None,
    detector: LanguageDetectorProtocol | None = None,
    store: TranslationStore | None = None,
    cache: TranslationCache | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    language_model = language_model or OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    detector = detector or LinguaDetector()
    store = store or PostgresTranslationStore(settings.database_url)
    cache = cache or RedisTranslationCache(settings.redis_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        store.prepare()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.language_model = language_model
    app.state.store = store
    app.state.cache = cache

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/translate", response_model=TranslateResponse)
    def translate(body: TranslateRequest) -> TranslateResponse:
        try:
            result = translate_message(
                text=body.text,
                source_language=body.source_language,
                target_language=body.target_language,
                model_name=body.model,
                settings=settings,
                language_model=language_model,
                detector=detector,
                cache=cache,
            )
        except TranslationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        try:
            store.save(_record(body.text, result))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=503, detail="Could not store the translation."
            ) from exc
        return _response(result)

    return app


def _record(original_text: str, result: Translation) -> TranslationRecord:
    return TranslationRecord(
        original_text=original_text,
        source_language=result.source_language,
        target_language=result.target_language,
        translation=result.translation,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_usd=result.estimated_cost_usd,
        cached=result.cached,
    )


def _response(result: Translation) -> TranslateResponse:
    return TranslateResponse(
        source_language=result.source_language,
        target_language=result.target_language,
        translation=result.translation,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_usd=result.estimated_cost_usd,
        cached=result.cached,
    )


app = create_app()
