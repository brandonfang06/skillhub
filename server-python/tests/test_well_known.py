from fastapi.testclient import TestClient

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
