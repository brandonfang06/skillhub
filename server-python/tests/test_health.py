from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_skillhub_envelope() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health", headers={"X-Request-Id": "req-test-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req-test-1"
    assert response.json() == {
        "code": 0,
        "msg": "response.success.health",
        "data": {"message": "UP"},
        "timestamp": response.json()["timestamp"],
        "requestId": "req-test-1",
    }


def test_health_generates_request_id_when_missing() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["X-Request-Id"]
    assert body["requestId"] == response.headers["X-Request-Id"]


def test_prometheus_metrics_endpoint_is_available_for_staging_smoke() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/metrics/prometheus")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "skillhub_python_backend_up 1" in response.text
