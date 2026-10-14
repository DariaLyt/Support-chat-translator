from fastapi.testclient import TestClient

from app.cache import MemoryTranslationCache
from app.config import Settings
from app.db import MemoryTranslationStore
from app.llm.fake import FakeLanguageModel
from app.main import create_app


class _Finnish:
    def detect(self, text: str) -> str | None:
        return "fi"


def _app(model: FakeLanguageModel) -> TestClient:
    settings = Settings(
        model_a_name="model-a",
        model_a_input_price_per_million=0.40,
        model_a_output_price_per_million=1.60,
        model_b_name="model-b",
        model_b_input_price_per_million=2.00,
        model_b_output_price_per_million=8.00,
    )
    return TestClient(
        create_app(
            settings,
            language_model=model,
            detector=_Finnish(),
            store=MemoryTranslationStore(),
            cache=MemoryTranslationCache(),
        )
    )


def _sample(body: str, name: str, model: str) -> float:
    prefix = f'{name}{{model="{model}"}}'
    for line in body.splitlines():
        if line.startswith(prefix):
            return float(line.split()[-1])
    raise AssertionError(f"{name} for {model} was not exported")


def test_successful_call_records_count_latency_and_cost() -> None:
    model = FakeLanguageModel(
        translation="The order is late", input_tokens=1000, output_tokens=500
    )
    client = _app(model)
    payload = {
        "text": "Tilaus on myöhässä",
        "source_language": "fi",
        "target_language": "en",
    }

    first = client.post("/translate", json=payload)
    second = client.post("/translate", json=payload)
    metrics = client.get("/metrics")

    assert first.status_code == 200
    assert second.json()["cached"] is True
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    body = metrics.text
    assert _sample(body, "translation_requests_total", "model-a") == 2
    assert _sample(body, "translation_latency_seconds_count", "model-a") == 2
    assert _sample(body, "translation_cost_usd_total", "model-a") == 0.0012


def test_rejected_call_is_not_counted() -> None:
    client = _app(FakeLanguageModel())

    response = client.post(
        "/translate",
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fi",
            "model": "missing-model",
        },
    )
    body = client.get("/metrics").text

    assert response.status_code == 422
    assert 'translation_requests_total{' not in body
