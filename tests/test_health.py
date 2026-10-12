from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_uses_injected_settings() -> None:
    app = create_app(Settings(app_name="test-translator"))

    assert app.title == "test-translator"
