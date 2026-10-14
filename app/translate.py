"""Detect the language, call the model interface, and price the result."""

import time
from dataclasses import dataclass

from app.cache import TranslationCache, cache_key
from app.config import Settings
from app.detection import LANGUAGE_NAMES, LanguageDetectorProtocol
from app.llm.base import (
    ChatMessage,
    CompletionRequest,
    LanguageModel,
    ModelError,
    ModelNotConfigured,
)
from app.pricing import ModelPrice, estimate_cost_usd

_SYSTEM_PROMPT = (
    "You translate customer support messages. "
    "Return only the translation, with no explanation. "
    "Keep order numbers, street addresses, and emoji unchanged."
)


@dataclass(frozen=True)
class Translation:
    source_language: str
    target_language: str
    translation: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cached: bool


class TranslationError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def translate_message(
    *,
    text: str,
    source_language: str,
    target_language: str,
    model_name: str | None,
    settings: Settings,
    language_model: LanguageModel,
    detector: LanguageDetectorProtocol,
    cache: TranslationCache,
) -> Translation:
    started = time.perf_counter()
    price = _select_price(settings, model_name)

    if source_language == "auto":
        detected = detector.detect(text)
        if detected is None:
            raise TranslationError(
                "Could not detect the language. Set source_language to fi or en.",
                422,
            )
        source_language = detected

    if source_language == target_language:
        return _result(
            started=started,
            source_language=source_language,
            target_language=target_language,
            translation=text,
            model=price.name,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            cached=False,
        )

    key = cache_key(price.name, source_language, target_language, text)
    cached_translation = cache.get(key)
    if cached_translation is not None:
        return _result(
            started=started,
            source_language=source_language,
            target_language=target_language,
            translation=cached_translation,
            model=price.name,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            cached=True,
        )

    try:
        completion = language_model.complete(
            CompletionRequest(
                model=price.name,
                messages=_messages(text, source_language, target_language),
            )
        )
    except ModelNotConfigured as exc:
        raise TranslationError(str(exc), 503) from exc
    except ModelError as exc:
        raise TranslationError(str(exc), 502) from exc

    cache.set(key, completion.text, settings.cache_ttl_seconds)
    return _result(
        started=started,
        source_language=source_language,
        target_language=target_language,
        translation=completion.text,
        model=price.name,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        estimated_cost_usd=estimate_cost_usd(
            price, completion.input_tokens, completion.output_tokens
        ),
        cached=False,
    )


def _select_price(settings: Settings, model_name: str | None) -> ModelPrice:
    prices = settings.model_prices()
    chosen = model_name or settings.model_a_name
    price = prices.get(chosen)
    if price is None:
        configured = ", ".join(prices)
        raise TranslationError(
            f"Unknown model '{chosen}'. Configured models: {configured}.",
            422,
        )
    return price


def _messages(text: str, source: str, target: str) -> tuple[ChatMessage, ...]:
    return (
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=(
                f"Translate from {LANGUAGE_NAMES[source]} to "
                f"{LANGUAGE_NAMES[target]}.\n\n{text}"
            ),
        ),
    )


def _result(
    *,
    started: float,
    source_language: str,
    target_language: str,
    translation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
    cached: bool,
) -> Translation:
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return Translation(
        source_language=source_language,
        target_language=target_language,
        translation=translation,
        model=model,
        latency_ms=elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        cached=cached,
    )
