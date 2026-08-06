import asyncio

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

from app.auth.session import (
    InMemorySessionStore,
    RedisSessionStore,
    _cookie_secure,
    clear_session,
    establish_session,
    read_session_principal,
)
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


def test_subpath_login_invalidates_a_lone_legacy_root_session_safely(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    monkeypatch.setenv("SKILLHUB_SESSION_COOKIE_SECURE", "true")
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    store = InMemorySessionStore()
    legacy_session_id = asyncio.run(store.create(principal("legacy-user")))
    app.state.auth_session_store = store
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("SESSION", legacy_session_id, domain="testserver.local", path="/")

    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )

    session_cookies = [cookie for cookie in client.cookies.jar if cookie.name == "SESSION"]
    assert login.status_code == 200
    assert [cookie.path for cookie in session_cookies] == ["/", "/skillhub"]
    assert session_cookies[0].value == legacy_session_id
    assert session_cookies[1].value != legacy_session_id
    assert asyncio.run(store.get(legacy_session_id)) is None


def test_subpath_login_preserves_a_foreign_root_session_cookie(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    monkeypatch.setenv("SKILLHUB_SESSION_COOKIE_SECURE", "true")
    app = create_app()
    app.state.local_auth_login = lambda payload: principal()
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("SESSION", "foreign-root-session", domain="testserver.local", path="/")

    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )

    session_cookies = {
        cookie.path: cookie.value
        for cookie in client.cookies.jar
        if cookie.name == "SESSION"
    }
    assert login.status_code == 200
    assert session_cookies["/"] == "foreign-root-session"
    assert session_cookies["/skillhub"] != "foreign-root-session"


def test_subpath_login_preserves_an_oversized_foreign_root_cookie(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    f"SESSION={scoped_session_id}; SESSION={'x' * 129}".encode(),
                )
            ],
        }
    )
    response = Response()

    asyncio.run(establish_session(request, response, principal()))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )


def test_subpath_login_does_not_treat_a_lone_scoped_session_as_root(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", f"SESSION={scoped_session_id}".encode())],
        }
    )
    response = Response()

    asyncio.run(establish_session(request, response, principal()))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )


def test_subpath_login_preserves_root_cookie_and_revokes_three_candidate_sessions(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    root_session_id = asyncio.run(store.create(principal("legacy-user")))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    f"SESSION=more-specific; SESSION={scoped_session_id}; SESSION={root_session_id}".encode(),
                )
            ],
        }
    )
    response = Response()

    asyncio.run(establish_session(request, response, principal()))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )
    assert asyncio.run(store.get(scoped_session_id)) is None
    assert asyncio.run(store.get(root_session_id)) is None


def test_establish_session_invalidates_existing_cookie_sessions(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")

    class FakeStore:
        def __init__(self) -> None:
            self.events: list[str] = []

        async def get(self, session_id: str) -> dict[str, object] | None:
            self.events.append(f"get:{session_id}")
            return principal("legacy-user") if session_id == "legacy-root-session" else None

        async def rotate(
            self,
            value: dict[str, object],
            existing_session_ids: list[str],
        ) -> str:
            self.events.append(
                f"rotate:{value['userId']}:{','.join(existing_session_ids)}"
            )
            return "new-session"

    app = create_app()
    store = FakeStore()
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", b"SESSION=scoped-session; SESSION=legacy-root-session")],
        }
    )

    response = Response()

    asyncio.run(establish_session(request, response, principal()))

    assert store.events == [
        "get:legacy-root-session",
        "rotate:session-user:scoped-session,legacy-root-session",
    ]
    assert any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )


def test_logout_clears_the_session_cookie_at_the_public_base_path(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    client = TestClient(app)

    logout = client.post("/api/v1/auth/logout")

    assert logout.status_code == 204
    assert "Path=/skillhub" in logout.headers["set-cookie"]


def test_subpath_logout_expires_scoped_and_legacy_root_session_cookies(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    legacy_session_id = asyncio.run(store.create(principal("legacy-user")))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    f"SESSION={scoped_session_id}; SESSION={legacy_session_id}".encode(),
                )
            ],
        }
    )
    response = Response()

    asyncio.run(clear_session(request, response))

    set_cookie_headers = response.headers.getlist("set-cookie")
    assert any("Path=/skillhub" in header for header in set_cookie_headers)
    assert any("Path=/;" in header for header in set_cookie_headers)
    assert asyncio.run(store.get(scoped_session_id)) is None
    assert asyncio.run(store.get(legacy_session_id)) is None


def test_subpath_logout_preserves_a_foreign_root_session_cookie(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("SESSION", "foreign-root-session", domain="testserver.local", path="/")

    logout = client.post("/api/v1/auth/logout")

    session_cookies = [cookie for cookie in client.cookies.jar if cookie.name == "SESSION"]
    assert logout.status_code == 204
    assert [(cookie.path, cookie.value) for cookie in session_cookies] == [
        ("/", "foreign-root-session")
    ]


def test_subpath_logout_preserves_an_oversized_foreign_root_cookie(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    f"SESSION={scoped_session_id}; SESSION={'x' * 129}".encode(),
                )
            ],
        }
    )
    response = Response()

    asyncio.run(clear_session(request, response))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )


def test_subpath_logout_does_not_treat_a_lone_scoped_session_as_root(monkeypatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", f"SESSION={scoped_session_id}".encode())],
        }
    )
    response = Response()

    asyncio.run(clear_session(request, response))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )


def test_subpath_logout_route_does_not_treat_a_lone_scoped_session_as_root(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    app.state.auth_session_store = store
    client = TestClient(app)

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"cookie": f"SESSION={scoped_session_id}"},
    )

    assert logout.status_code == 204
    assert not any(
        "Path=/;" in header for header in logout.headers.get_list("set-cookie")
    )


def test_subpath_logout_route_rejects_cookie_overflow_before_mutation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    root_session_id = asyncio.run(store.create(principal("legacy-user")))
    app.state.auth_session_store = store
    client = TestClient(app)

    logout = client.post(
        "/api/v1/auth/logout",
        headers={
            "cookie": (
                "SESSION=more-1; SESSION=more-2; "
                f"SESSION={scoped_session_id}; SESSION={root_session_id}"
            )
        },
    )

    assert logout.status_code == 400
    assert logout.json()["detail"] == "error.auth.session.cookieOverflow"
    assert logout.headers.get_list("set-cookie") == []
    assert asyncio.run(store.get(scoped_session_id)) is not None
    assert asyncio.run(store.get(root_session_id)) is not None


def test_subpath_logout_preserves_root_cookie_and_revokes_three_candidate_sessions(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    store = InMemorySessionStore()
    scoped_session_id = asyncio.run(store.create(principal()))
    root_session_id = asyncio.run(store.create(principal("legacy-user")))
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    f"SESSION=more-specific; SESSION={scoped_session_id}; SESSION={root_session_id}".encode(),
                )
            ],
        }
    )
    response = Response()

    asyncio.run(clear_session(request, response))

    assert not any(
        "Path=/;" in header for header in response.headers.getlist("set-cookie")
    )
    assert asyncio.run(store.get(scoped_session_id)) is None
    assert asyncio.run(store.get(root_session_id)) is None
    root_only_request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", f"SESSION={root_session_id}".encode())],
        }
    )
    assert asyncio.run(read_session_principal(root_only_request)) is None


def test_duplicate_session_cookies_prefer_the_scoped_session() -> None:
    class FakeStore:
        async def get(self, session_id: str) -> dict[str, object] | None:
            return principal() if session_id == "scoped-session" else None

    app = create_app()
    app.state.auth_session_store = FakeStore()
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", b"SESSION=scoped-session; SESSION=expired-root-session")],
        }
    )

    assert asyncio.run(read_session_principal(request)) == principal()


def test_session_lookup_limits_duplicate_cookie_candidates() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.read: list[str] = []

        async def get(self, session_id: str) -> None:
            self.read.append(session_id)

    app = create_app()
    store = FakeStore()
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    b"SESSION=first; SESSION=second; SESSION=attacker-controlled",
                )
            ],
        }
    )

    assert asyncio.run(read_session_principal(request)) is None
    assert store.read == ["first", "second"]


def test_logout_invalidates_every_session_id_from_duplicate_cookies() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def get(self, session_id: str) -> None:
            return None

        async def delete_many(self, session_ids: list[str]) -> None:
            self.deleted.extend(session_ids)

    app = create_app()
    store = FakeStore()
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", b"SESSION=scoped-session; SESSION=legacy-root-session")],
        }
    )

    asyncio.run(clear_session(request, Response()))

    assert store.deleted == ["scoped-session", "legacy-root-session"]


def test_logout_limits_duplicate_cookie_deletions_to_three_candidates() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def get(self, session_id: str) -> None:
            return None

        async def delete(self, session_id: str) -> None:
            self.deleted.append(session_id)

        async def delete_many(self, session_ids: list[str]) -> None:
            self.deleted.extend(session_ids)

    app = create_app()
    store = FakeStore()
    app.state.auth_session_store = store
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [
                (
                    b"cookie",
                    b"SESSION=first; SESSION=second; SESSION=attacker-controlled",
                )
            ],
        }
    )

    asyncio.run(clear_session(request, Response()))

    assert store.deleted == ["first", "second", "attacker-controlled"]


def test_logout_does_not_clear_cookies_when_root_ownership_lookup_fails(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")

    class FakeStore:
        async def get(self, session_id: str) -> None:
            raise RuntimeError("redis get failed")

        async def delete_many(self, session_ids: list[str]) -> None:
            raise AssertionError("delete must not run after ownership lookup failure")

    app = create_app()
    app.state.auth_session_store = FakeStore()
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", b"SESSION=scoped; SESSION=root")],
        }
    )
    response = Response()

    with pytest.raises(RuntimeError, match="redis get failed"):
        asyncio.run(clear_session(request, response))

    assert response.headers.getlist("set-cookie") == []


def test_logout_does_not_clear_cookies_when_session_deletion_fails(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")

    class FakeStore:
        async def get(self, session_id: str) -> None:
            return None

        async def delete_many(self, session_ids: list[str]) -> None:
            raise RuntimeError("redis delete failed")

    app = create_app()
    app.state.auth_session_store = FakeStore()
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"cookie", b"SESSION=scoped; SESSION=root")],
        }
    )
    response = Response()

    with pytest.raises(RuntimeError, match="redis delete failed"):
        asyncio.run(clear_session(request, response))

    assert response.headers.getlist("set-cookie") == []


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


def test_local_register_rejects_cookie_overflow_before_registration() -> None:
    app = create_app()
    registrar_calls: list[dict[str, object]] = []
    app.state.local_auth_registrar = lambda payload: registrar_calls.append(payload) or principal()
    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/local/register",
        headers={"cookie": "SESSION=one; SESSION=two; SESSION=three; SESSION=four"},
        json={"username": "session-user", "password": "Abcd123!", "email": "session-user@example.test"},
    )

    assert register.status_code == 400
    assert register.json()["detail"] == "error.auth.session.cookieOverflow"
    assert registrar_calls == []


def test_local_login_rejects_cookie_overflow_before_credentials_are_checked() -> None:
    app = create_app()
    login_calls: list[dict[str, object]] = []
    app.state.local_auth_login = lambda payload: login_calls.append(payload) or principal()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/local/login",
        headers={"cookie": "SESSION=one; SESSION=two; SESSION=three; SESSION=four"},
        json={"username": "session-user", "password": "Abcd123!"},
    )

    assert login.status_code == 400
    assert login.json()["detail"] == "error.auth.session.cookieOverflow"
    assert login_calls == []


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


def test_direct_login_rejects_cookie_overflow_before_credentials_are_checked() -> None:
    app = create_app()
    app.state.auth_direct_enabled = True
    login_calls: list[dict[str, object]] = []
    app.state.local_auth_login = lambda payload: login_calls.append(payload) or principal()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/direct/login",
        headers={"cookie": "SESSION=one; SESSION=two; SESSION=three; SESSION=four"},
        json={"provider": "local", "username": "session-user", "password": "Abcd123!"},
    )

    assert login.status_code == 400
    assert login.json()["detail"] == "error.auth.session.cookieOverflow"
    assert login_calls == []


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


def test_redis_session_rotation_is_atomic_when_transaction_execution_fails() -> None:
    class FailingPipeline:
        def setex(self, key: str, ttl: int, value: str) -> "FailingPipeline":
            return self

        def delete(self, *keys: str) -> "FailingPipeline":
            return self

        async def execute(self) -> None:
            raise RuntimeError("redis transaction failed")

    class FakeRedis:
        def __init__(self) -> None:
            self.values = {
                "test:session:first": "first-principal",
                "test:session:second": "second-principal",
            }
            self.transaction_flags: list[bool] = []

        def pipeline(self, *, transaction: bool) -> FailingPipeline:
            self.transaction_flags.append(transaction)
            return FailingPipeline()

    async def scenario() -> None:
        redis = FakeRedis()
        store = RedisSessionStore(redis, ttl_seconds=60, key_prefix="test:session:")

        try:
            await store.rotate(principal(), ["first", "second"])
        except RuntimeError as exc:
            assert str(exc) == "redis transaction failed"
        else:
            raise AssertionError("rotation failure must be propagated")

        assert redis.transaction_flags == [True]
        assert redis.values == {
            "test:session:first": "first-principal",
            "test:session:second": "second-principal",
        }

    asyncio.run(scenario())
