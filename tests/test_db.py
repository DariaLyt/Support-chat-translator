from fastapi.testclient import TestClient

from app.cache import MemoryTranslationCache
from app.config import Settings
from app.db import PostgresTranslationStore
from app.llm.fake import FakeLanguageModel
from app.main import create_app

_TEXT = "postgres-persist-check: Tilaus on myöhässä"


class _Finnish:
    def detect(self, text: str) -> str | None:
        return "fi"


def test_translate_is_stored_in_postgres() -> None:
    settings = Settings(
        model_a_name="gpt-4.1-mini",
        model_a_input_price_per_million=0.40,
        model_a_output_price_per_million=1.60,
        model_b_name="gpt-4.1",
        model_b_input_price_per_million=2.00,
        model_b_output_price_per_million=8.00,
    )
    store = PostgresTranslationStore(settings.database_url)
    store.prepare()
    store.delete_by_original_text(_TEXT)
    model = FakeLanguageModel(
        translation="The order is late", input_tokens=1000, output_tokens=500
    )
    app = create_app(
        settings,
        language_model=model,
        detector=_Finnish(),
        store=store,
        cache=MemoryTranslationCache(),
    )

    try:
        response = TestClient(app).post(
            "/translate",
            json={
                "text": _TEXT,
                "source_language": "auto",
                "target_language": "en",
            },
        )

        assert response.status_code == 200
        saved = store.find_by_original_text(_TEXT)
        assert len(saved) == 1
        row = saved[0]
        body = response.json()
        assert row.original_text == _TEXT
        assert row.source_language == "fi"
        assert row.target_language == "en"
        assert row.translation == "The order is late"
        assert row.model == "gpt-4.1-mini"
        assert row.latency_ms == body["latency_ms"]
        assert row.input_tokens == 1000
        assert row.output_tokens == 500
        assert row.estimated_cost_usd == 0.0012
        assert row.cached is False
    finally:
        store.delete_by_original_text(_TEXT)
