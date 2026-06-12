from fastapi.testclient import TestClient

from app.main import create_app


def principal(user_id: str = "session-user", *, provider: str = "local") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "Session User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": provider,
        "platformRoles": ["USER"],
    }


def test_local_login_creates_session_cookie_used_by_auth_me() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )
    auth_me = client.get("/api/v1/auth/me")

    assert login.status_code == 200
    assert "SESSION" in client.cookies
    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == principal()


def test_mock_user_header_takes_precedence_over_session_cookie() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    app.state.auth_me_reader = lambda user_id: principal(user_id, provider="mock")
    client = TestClient(app)

    client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )
    auth_me = client.get("/api/v1/auth/me", headers={"X-Mock-User-Id": "mock-user"})

    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == principal("mock-user", provider="mock")


def test_bearer_token_takes_precedence_over_session_cookie() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    app.state.auth_bearer_reader = lambda raw_token: principal("bearer-user", provider="api_token")
    client = TestClient(app)

    client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )
    auth_me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer sk_valid"})

    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == principal("bearer-user", provider="api_token")


def test_logout_invalidates_session_cookie() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    client = TestClient(app)

    client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )
    logout = client.post("/api/v1/auth/logout")
    auth_me = client.get("/api/v1/auth/me")

    assert logout.status_code == 204
    assert "SESSION" not in client.cookies
    assert auth_me.status_code == 401


def test_direct_login_creates_session_cookie_used_by_auth_me() -> None:
    app = create_app()
    app.state.auth_direct_enabled = True
    app.state.local_auth_login = lambda payload: principal()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/direct/login",
        json={"provider": "local", "username": "session-user", "password": "Abcd123!"},
    )
    auth_me = client.get("/api/v1/auth/me")

    assert login.status_code == 200
    assert "SESSION" in client.cookies
    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == principal()
