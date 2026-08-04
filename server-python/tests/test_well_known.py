from fastapi.testclient import TestClient
import pytest

from app.main import create_app


def test_clawhub_well_known_returns_plain_discovery_json() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/.well-known/clawhub.json",
        headers={"X-Request-Id": "well-known-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "well-known-test"
    assert response.json() == {"apiBase": "/api/v1"}


def test_clawhub_well_known_uses_the_public_base_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    client = TestClient(create_app())

    response = client.get("/.well-known/clawhub.json")

    assert response.status_code == 200
    assert response.json() == {"apiBase": "/skillhub/api/v1"}
