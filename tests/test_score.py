import pytest

from app.config import Settings
from app.db import MemoryTranslationStore
from app.llm.base import Completion, CompletionRequest
from eval.dataset import LabeledMessage
from eval.score import (
    Outcome,
    evaluate,
    meaning_passes,
    percentile,
    render_table,
    replace_scorecard,
    summarize,
)


def _message(text: str, reference: str, facts: tuple[str, ...], protected: tuple[str, ...] = ()) -> LabeledMessage:
    return LabeledMessage(
        id=text,
        speaker="customer",
        text=text,
        source_language="fi",
        target_language="en",
        mixed=False,
        rude=False,
        reference=reference,
        protected=protected,
        facts=facts,
    )


class _ScriptedModel:
    def __init__(self, translations: dict[str, str]) -> None:
        self.translations = translations
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        original = request.messages[-1].content.split("\n\n", 1)[1]
        return Completion(
            text=self.translations[original],
            model=request.model,
            input_tokens=1000,
            output_tokens=500,
        )


def test_meaning_requires_facts_and_protected_strings() -> None:
    message = _message(
        "Tilaus #48291 on myöhässä, osoite Mannerheimintie 12",
        "Order #48291 is late, address Mannerheimintie 12",
        ("is late",),
        ("#48291", "Mannerheimintie 12"),
    )

    assert meaning_passes(message, "Order #48291 is late, address Mannerheimintie 12")
    assert meaning_passes(message, "ORDER #48291 IS LATE, address Mannerheimintie 12")
    assert not meaning_passes(message, "Order #48291 is late, address Mannerheimintie 13")
    assert not meaning_passes(message, "Order #48291 is here, address Mannerheimintie 12")


def test_percentile_uses_linear_rank() -> None:
    assert percentile([10], 0.95) == 10
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10, 20, 30, 40, 100], 0.95) == 88


def test_summary_splits_meaning_from_latency_and_cost() -> None:
    card = summarize(
        "model-a",
        [
            Outcome(True, 10, 0.10),
            Outcome(True, 20, 0.10),
            Outcome(False, 30, 0.10),
            Outcome(True, 40, 0.10),
            Outcome(False, 100, 0.20),
        ],
    )

    assert card.passed == 3
    assert card.total == 5
    assert card.median_latency_ms == 30
    assert card.p95_latency_ms == 88
    assert card.mean_cost_usd == pytest.approx(0.12)
    assert card.total_cost_usd == pytest.approx(0.6)


def test_evaluation_scores_both_models_and_stores_each_call() -> None:
    messages = [
        _message("Tilaus on myöhässä", "The order is late", ("is late",)),
        _message("Ruoka oli kylmää", "The food was cold", ("food was cold",)),
    ]
    settings = Settings(
        model_a_name="model-a",
        model_a_input_price_per_million=0.40,
        model_a_output_price_per_million=1.60,
        model_b_name="model-b",
        model_b_input_price_per_million=2.00,
        model_b_output_price_per_million=8.00,
    )
    model = _ScriptedModel(
        {
            "Tilaus on myöhässä": "The order is late",
            "Ruoka oli kylmää": "Something else",
        }
    )
    store = MemoryTranslationStore()

    cards = evaluate(messages, settings=settings, language_model=model, store=store)

    assert [card.model for card in cards] == ["model-a", "model-b"]
    assert cards[0].passed == 1
    assert cards[0].total == 2
    assert cards[0].total_cost_usd == 0.0024
    assert cards[1].passed == 1
    assert cards[1].total_cost_usd == 0.012
    assert [request.model for request in model.requests] == [
        "model-a",
        "model-a",
        "model-b",
        "model-b",
    ]
    assert len(store.records) == 4
    assert store.records[0].latency_ms >= 0
    assert store.records[0].estimated_cost_usd == 0.0012
    assert store.records[0].cached is False


def test_table_replaces_only_the_scorecard() -> None:
    markdown = "\n".join(
        [
            "## Quality",
            "",
            "| Model | Meaning | Median latency | p95 latency | Mean cost | Total cost |",
            "| --- | --- | --- | --- | --- | --- |",
            "| _filled by the evaluation script_ | | | | | |",
            "",
            "## Stack",
            "",
        ]
    )
    card = summarize("model-a", [Outcome(True, 12, 0.0012)])

    updated = replace_scorecard(markdown, render_table([card]))

    assert "| model-a | 1/1 | 12 ms | 12 ms | $0.001200 | $0.001200 |" in updated
    assert "_filled by the evaluation script_" not in updated
    assert updated.endswith("## Stack\n")
