from fastapi.testclient import TestClient

from app.main import create_app


def auth_me_response() -> dict[str, object]:
    return {
        "userId": "local-user",
        "displayName": "Local User",
        "email": "local-user@example.com",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_auth_me_route_returns_envelope_for_mock_user() -> None:
    app = create_app()
    seen_user_ids: list[str] = []

    def reader(user_id: str) -> dict[str, object] | None:
        seen_user_ids.append(user_id)
        return auth_me_response()

    app.state.auth_me_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/auth/me",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "auth-me-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "auth-me-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "auth-me-test"
    assert response.json()["data"] == auth_me_response()
    assert seen_user_ids == ["local-user"]


def test_auth_me_route_returns_401_when_mock_user_header_missing() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_me_response()

    client = TestClient(app)
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_auth_me_route_returns_401_when_mock_user_header_blank() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_me_response()

    client = TestClient(app)
    response = client.get("/api/v1/auth/me", headers={"X-Mock-User-Id": "   "})

    assert response.status_code == 401


def test_auth_me_route_returns_401_when_mock_user_not_found() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: None

    client = TestClient(app)
    response = client.get("/api/v1/auth/me", headers={"X-Mock-User-Id": "missing"})

    assert response.status_code == 401
