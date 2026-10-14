import json

import httpx2
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.base import CompletionRequest
from app.llm.fake import FakeLanguageModel
from app.llm.openai_client import OpenAICompatibleClient
from app.main import create_app


class StubDetector:
    def __init__(self, code: str | None) -> None:
        self.code = code
        self.calls: list[str] = []

    def detect(self, text: str) -> str | None:
        self.calls.append(text)
        return self.code


def _settings() -> Settings:
    return Settings(
        llm_api_key="",
        model_a_name="model-a",
        model_a_input_price_per_million=0.40,
        model_a_output_price_per_million=1.60,
        model_b_name="model-b",
        model_b_input_price_per_million=2.00,
        model_b_output_price_per_million=8.00,
    )


def _client(
    model: FakeLanguageModel,
    detector: StubDetector | None = None,
    settings: Settings | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            settings or _settings(),
            language_model=model,
            detector=detector or StubDetector("fi"),
        )
    )


def test_translate_detects_then_calls_the_configured_model() -> None:
    model = FakeLanguageModel(
        translation="The order is late", input_tokens=1000, output_tokens=500
    )
    detector = StubDetector("fi")

    response = _client(model, detector).post(
        "/translate",
        json={
            "text": "Tilaus on myöhässä",
            "source_language": "auto",
            "target_language": "en",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_language"] == "fi"
    assert body["target_language"] == "en"
    assert body["translation"] == "The order is late"
    assert body["model"] == "model-a"
    assert body["input_tokens"] == 1000
    assert body["output_tokens"] == 500
    assert body["estimated_cost_usd"] == 0.0012
    assert body["cached"] is False
    assert body["latency_ms"] >= 0
    assert detector.calls == ["Tilaus on myöhässä"]
    request = model.requests[0]
    assert request.model == "model-a"
    assert request.messages[0].content.startswith("You translate customer support")
    assert "order numbers" in request.messages[0].content
    assert "Translate from Finnish to English." in request.messages[1].content


def test_explicit_source_language_skips_detection() -> None:
    model = FakeLanguageModel(translation="Hei")
    detector = StubDetector("en")

    response = _client(model, detector).post(
        "/translate",
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fi",
        },
    )

    assert response.status_code == 200
    assert response.json()["source_language"] == "en"
    assert detector.calls == []
    assert "Translate from English to Finnish." in model.requests[0].messages[1].content


def test_request_can_target_the_second_configured_model() -> None:
    model = FakeLanguageModel(input_tokens=1_000_000, output_tokens=0)

    response = _client(model).post(
        "/translate",
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fi",
            "model": "model-b",
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "model-b"
    assert response.json()["estimated_cost_usd"] == 2.0
    assert model.requests[0].model == "model-b"


def test_same_language_skips_the_model() -> None:
    model = FakeLanguageModel()

    response = _client(model, StubDetector("en")).post(
        "/translate",
        json={
            "text": "Where is my order?",
            "source_language": "auto",
            "target_language": "en",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["translation"] == "Where is my order?"
    assert body["input_tokens"] == 0
    assert body["output_tokens"] == 0
    assert body["estimated_cost_usd"] == 0.0
    assert model.requests == []


def test_unknown_model_is_rejected() -> None:
    response = _client(FakeLanguageModel()).post(
        "/translate",
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fi",
            "model": "missing-model",
        },
    )

    assert response.status_code == 422
    assert "Unknown model" in response.json()["detail"]


def test_undetected_language_is_rejected_before_the_model_call() -> None:
    model = FakeLanguageModel()

    response = _client(model, StubDetector(None)).post(
        "/translate",
        json={"text": "👍", "source_language": "auto", "target_language": "en"},
    )

    assert response.status_code == 422
    assert model.requests == []


def test_missing_api_key_does_not_call_the_provider() -> None:
    called = False

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal called
        called = True
        return httpx2.Response(500)

    client = OpenAICompatibleClient(
        base_url="https://api.openai.com/v1",
        api_key="",
        http=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    app = create_app(_settings(), language_model=client, detector=StubDetector("fi"))

    response = TestClient(app).post(
        "/translate",
        json={"text": "Hei", "source_language": "fi", "target_language": "en"},
    )

    assert response.status_code == 503
    assert called is False


def test_openai_client_sends_the_selected_model_and_reads_usage() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx2.Response(
            200,
            json={
                "model": "gpt-4.1",
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "Order "},
                                {"type": "text", "text": "#48291 is late"},
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 6},
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://api.openai.com/v1/",
        api_key="test-key",
        http=httpx2.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx2.MockTransport(handler),
        ),
    )
    completion = client.complete(
        CompletionRequest(model="gpt-4.1", messages=())
    )

    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"] == {
        "model": "gpt-4.1",
        "temperature": 0,
        "messages": [],
    }
    assert completion.text == "Order #48291 is late"
    assert completion.model == "gpt-4.1"
    assert completion.input_tokens == 20
    assert completion.output_tokens == 6


def test_provider_error_becomes_a_bad_gateway() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, json={"error": {"message": "slow down"}})

    client = OpenAICompatibleClient(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        http=httpx2.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx2.MockTransport(handler),
        ),
    )
    app = create_app(_settings(), language_model=client, detector=StubDetector("fi"))

    response = TestClient(app).post(
        "/translate",
        json={"text": "Hei", "source_language": "fi", "target_language": "en"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Model request failed with status 429"


def test_real_detector_recognizes_finnish_and_english() -> None:
    from app.detection import LinguaDetector

    detector = LinguaDetector()

    assert detector.detect("Tilaus on myöhässä ja osoite on väärä") == "fi"
    assert detector.detect("The courier cannot find the street address") == "en"
