import asyncio

from fastapi.testclient import TestClient

from app.auth.session import RedisSessionStore, _cookie_secure
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


def auth_me_principal(user_id: str = "session-user", *, provider: str = "local", can_change_password: bool) -> dict[str, object]:
    data = principal(user_id, provider=provider)
    data["canChangePassword"] = can_change_password
    return data


def test_cookie_secure_accepts_java_session_env(monkeypatch) -> None:
    monkeypatch.delenv("SKILLHUB_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    assert _cookie_secure() is True


def test_cookie_secure_ignores_a_blank_canonical_value_before_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_SESSION_COOKIE_SECURE", "   ")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    assert _cookie_secure() is True


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
    assert auth_me.json()["data"] == auth_me_principal(can_change_password=True)


def test_session_cookie_uses_the_public_base_path(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    monkeypatch.setenv("SKILLHUB_SESSION_COOKIE_SECURE", "true")
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )

    cookie = login.headers["set-cookie"]
    assert "Path=/skillhub" in cookie
    assert "Secure" in cookie


def test_logout_clears_the_session_cookie_at_the_public_base_path(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    client = TestClient(app)

    logout = client.post("/api/v1/auth/logout")

    assert logout.status_code == 204
    assert "Path=/skillhub" in logout.headers["set-cookie"]


def test_local_register_creates_session_cookie_used_by_auth_me() -> None:
    app = create_app()
    app.state.local_auth_registrar = lambda payload: principal()
    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/local/register",
        json={"username": "session-user", "password": "Abcd123!", "email": "session-user@example.test"},
    )
    auth_me = client.get("/api/v1/auth/me")

    assert register.status_code == 200
    assert "SESSION" in client.cookies
    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == auth_me_principal(can_change_password=True)


def test_change_password_accepts_session_principal() -> None:
    app = create_app()
    calls: list[tuple[str, dict[str, object]]] = []
    app.state.local_auth_login = lambda payload: principal()
    app.state.local_auth_password_changer = lambda user_id, payload: calls.append((user_id, payload))
    client = TestClient(app)

    client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )
    changed = client.post(
        "/api/v1/auth/local/change-password",
        json={"currentPassword": "Abcd123!", "newPassword": "Newpass123!"},
    )

    assert changed.status_code == 200
    assert calls == [("session-user", {"currentPassword": "Abcd123!", "newPassword": "Newpass123!"})]


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
    assert auth_me.json()["data"] == auth_me_principal("mock-user", provider="mock", can_change_password=False)


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
    assert auth_me.json()["data"] == auth_me_principal("bearer-user", provider="api_token", can_change_password=False)


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
    assert auth_me.json()["data"] == auth_me_principal(can_change_password=True)


def test_redis_session_store_serializes_principals_with_ttl() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.ttls: dict[str, int] = {}

        async def setex(self, key: str, ttl: int, value: str) -> None:
            self.values[key] = value
            self.ttls[key] = ttl

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def delete(self, key: str) -> None:
            self.values.pop(key, None)

    async def scenario() -> None:
        redis = FakeRedis()
        store = RedisSessionStore(redis, ttl_seconds=60, key_prefix="test:session:")

        session_id = await store.create(principal())
        loaded = await store.get(session_id)
        await store.delete(session_id)

        assert loaded == principal()
        assert redis.ttls[f"test:session:{session_id}"] == 60
        assert await store.get(session_id) is None

    asyncio.run(scenario())
