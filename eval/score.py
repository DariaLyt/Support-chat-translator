"""Score both configured models on meaning, latency, and cost."""

import math
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.db import PostgresTranslationStore, TranslationRecord, TranslationStore
from app.detection import LanguageDetectorProtocol
from app.llm.base import LanguageModel
from app.llm.openai_client import OpenAICompatibleClient
from app.translate import translate_message
from eval.dataset import LabeledMessage, load_messages

README_PATH = Path(__file__).resolve().parents[1] / "README.md"
_TABLE_HEADER = (
    "| Model | Meaning | Median latency | p95 latency | Mean cost | Total cost |"
)


@dataclass(frozen=True)
class Outcome:
    passed: bool
    latency_ms: int
    cost_usd: float


@dataclass(frozen=True)
class Scorecard:
    model: str
    passed: int
    total: int
    median_latency_ms: float
    p95_latency_ms: float
    mean_cost_usd: float
    total_cost_usd: float


class _NoCache:
    """Skip Redis so a repeated evaluation measures the model, not a cache hit."""

    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, translation: str, ttl_seconds: int) -> None:
        return None


class _SkipDetector:
    def detect(self, text: str) -> str | None:
        raise RuntimeError("labeled messages pass the source language explicitly")


def meaning_passes(message: LabeledMessage, translation: str) -> bool:
    folded = translation.casefold()
    facts_present = all(fact.casefold() in folded for fact in message.facts)
    protected_present = all(item in translation for item in message.protected)
    return facts_present and protected_present


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of an empty list")
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * fraction
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize(model: str, outcomes: list[Outcome]) -> Scorecard:
    latencies = [float(outcome.latency_ms) for outcome in outcomes]
    costs = [outcome.cost_usd for outcome in outcomes]
    total_cost = sum(costs)
    return Scorecard(
        model=model,
        passed=sum(1 for outcome in outcomes if outcome.passed),
        total=len(outcomes),
        median_latency_ms=percentile(latencies, 0.5),
        p95_latency_ms=percentile(latencies, 0.95),
        mean_cost_usd=total_cost / len(outcomes),
        total_cost_usd=total_cost,
    )


def evaluate_model(
    messages: list[LabeledMessage],
    *,
    model_name: str,
    settings: Settings,
    language_model: LanguageModel,
    store: TranslationStore,
    detector: LanguageDetectorProtocol | None = None,
) -> list[Outcome]:
    detector = detector or _SkipDetector()
    cache = _NoCache()
    outcomes: list[Outcome] = []
    for message in messages:
        result = translate_message(
            text=message.text,
            source_language=message.source_language,
            target_language=message.target_language,
            model_name=model_name,
            settings=settings,
            language_model=language_model,
            detector=detector,
            cache=cache,
        )
        store.save(
            TranslationRecord(
                original_text=message.text,
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
        )
        outcomes.append(
            Outcome(
                passed=meaning_passes(message, result.translation),
                latency_ms=result.latency_ms,
                cost_usd=result.estimated_cost_usd,
            )
        )
    return outcomes


def evaluate(
    messages: list[LabeledMessage],
    *,
    settings: Settings,
    language_model: LanguageModel,
    store: TranslationStore,
) -> list[Scorecard]:
    return [
        summarize(
            model_name,
            evaluate_model(
                messages,
                model_name=model_name,
                settings=settings,
                language_model=language_model,
                store=store,
            ),
        )
        for model_name in (settings.model_a_name, settings.model_b_name)
    ]


def render_table(scorecards: list[Scorecard]) -> str:
    lines = [_TABLE_HEADER, "| --- | --- | --- | --- | --- | --- |"]
    for card in scorecards:
        lines.append(
            "| {model} | {passed}/{total} | {median} ms | {p95} ms | {mean} | {total_cost} |".format(
                model=card.model,
                passed=card.passed,
                total=card.total,
                median=round(card.median_latency_ms),
                p95=round(card.p95_latency_ms),
                mean=_usd(card.mean_cost_usd),
                total_cost=_usd(card.total_cost_usd),
            )
        )
    return "\n".join(lines)


def replace_scorecard(markdown: str, table: str) -> str:
    lines = markdown.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith(_TABLE_HEADER)
    )
    end = start + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    updated = lines[:start] + table.splitlines() + lines[end:]
    text = "\n".join(updated)
    if markdown.endswith("\n"):
        text += "\n"
    return text


def write_scorecard(scorecards: list[Scorecard], readme_path: Path = README_PATH) -> None:
    readme_path.write_text(
        replace_scorecard(readme_path.read_text(encoding="utf-8"), render_table(scorecards)),
        encoding="utf-8",
    )


def _usd(amount: float) -> str:
    return f"${amount:.6f}"


def main() -> None:
    settings = Settings()
    if not settings.llm_api_key:
        raise SystemExit("Set LLM_API_KEY in .env, then run the evaluation again.")
    messages = load_messages()
    store = PostgresTranslationStore(settings.database_url)
    store.prepare()
    scorecards = evaluate(
        messages,
        settings=settings,
        language_model=OpenAICompatibleClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        ),
        store=store,
    )
    write_scorecard(scorecards)
    for card in scorecards:
        print(
            f"{card.model}: {card.passed}/{card.total} "
            f"median {round(card.median_latency_ms)} ms "
            f"total {_usd(card.total_cost_usd)}"
        )


if __name__ == "__main__":
    main()
