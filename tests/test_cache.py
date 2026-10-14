from redis.exceptions import RedisError
from fastapi.testclient import TestClient

from app.cache import RedisTranslationCache, cache_key
from app.config import Settings
from app.db import MemoryTranslationStore
from app.llm.fake import FakeLanguageModel
from app.main import create_app

_TEXT = "redis-cache-check: Tilaus on myöhässä"


class _Finnish:
    def detect(self, text: str) -> str | None:
        return "fi"


class _DownRedis:
    def get(self, key: str) -> str | None:
        raise RedisError("down")

    def set(self, key: str, value: str, ex: int) -> None:
        raise RedisError("down")


def test_repeat_call_is_served_from_redis() -> None:
    settings = Settings(cache_ttl_seconds=600)
    cache = RedisTranslationCache(settings.redis_url)
    key = cache_key("gpt-4.1-mini", "fi", "en", _TEXT)
    cache.delete(key)
    model = FakeLanguageModel(
        translation="The order is late", input_tokens=12, output_tokens=4
    )
    app = create_app(
        settings,
        language_model=model,
        detector=_Finnish(),
        store=MemoryTranslationStore(),
        cache=cache,
    )
    payload = {
        "text": _TEXT,
        "source_language": "auto",
        "target_language": "en",
    }

    try:
        with TestClient(app) as client:
            first = client.post("/translate", json=payload)
            second = client.post("/translate", json=payload)

        assert first.status_code == 200
        assert first.json()["cached"] is False
        assert second.status_code == 200
        assert second.json()["cached"] is True
        assert second.json()["translation"] == "The order is late"
        assert second.json()["input_tokens"] == 0
        assert second.json()["estimated_cost_usd"] == 0.0
        assert len(model.requests) == 1
        assert 0 < cache.ttl(key) <= 600
    finally:
        cache.delete(key)


def test_redis_outage_still_translates() -> None:
    cache = RedisTranslationCache("redis://localhost:6379/0", client=_DownRedis())
    model = FakeLanguageModel(translation="The order is late")
    app = create_app(
        Settings(),
        language_model=model,
        detector=_Finnish(),
        store=MemoryTranslationStore(),
        cache=cache,
    )

    response = TestClient(app).post(
        "/translate",
        json={"text": "Hei", "source_language": "fi", "target_language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert response.json()["translation"] == "The order is late"
    assert len(model.requests) == 1
