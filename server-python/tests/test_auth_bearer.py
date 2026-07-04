from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.auth.tokens import sha256_token
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeContext:
    def __init__(self, connection: "FakeBearerConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeBearerConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeBearerEngine:
    def __init__(self, connection: "FakeBearerConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeBearerConnection:
    def __init__(self) -> None:
        self.token_rows: list[dict[str, Any]] = []
        self.role_rows: list[dict[str, Any]] = []
        self.updated_token_ids: list[int] = []
        self.seen_hashes: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        bound = params or {}
        if "FROM api_token" in sql and "JOIN user_account" in sql:
            self.seen_hashes.append(str(bound["token_hash"]))
            return FakeResult(self.token_rows)
        if "FROM user_role_binding" in sql:
            return FakeResult(self.role_rows)
        if sql.startswith("UPDATE api_token SET last_used_at"):
            self.updated_token_ids.append(int(bound["token_id"]))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def active_token_row(raw_token: str = "sk_valid-token") -> dict[str, Any]:
    return {
        "token_id": 42,
        "id": "token-user",
        "display_name": "Token User",
        "email": "token-user@example.test",
        "avatar_url": "",
        "scope_json": ["skill:read", "skill:publish"],
    }


def test_read_current_bearer_user_hashes_token_reads_roles_and_touches_last_used() -> None:
    from app.api.auth import read_current_bearer_user

    connection = FakeBearerConnection()
    connection.token_rows = [active_token_row()]
    connection.role_rows = [{"code": "SKILL_ADMIN"}]

    data = asyncio.run(read_current_bearer_user(FakeBearerEngine(connection), "sk_valid-token"))

    assert data == {
        "userId": "token-user",
        "displayName": "Token User",
        "email": "token-user@example.test",
        "avatarUrl": "",
        "oauthProvider": "api_token",
        "canChangePassword": False,
        "platformRoles": ["SKILL_ADMIN"],
        "tokenScopes": ["skill:read", "skill:publish"],
    }
    assert connection.seen_hashes == [sha256_token("sk_valid-token")]
    assert connection.updated_token_ids == [42]


def test_read_current_bearer_user_returns_none_for_invalid_token() -> None:
    from app.api.auth import read_current_bearer_user

    connection = FakeBearerConnection()

    data = asyncio.run(read_current_bearer_user(FakeBearerEngine(connection), "sk_missing"))

    assert data is None
    assert connection.updated_token_ids == []


def test_current_principal_routes_accept_bearer_token_and_preserve_shapes() -> None:
    app = create_app()

    def bearer_reader(raw_token: str) -> dict[str, object] | None:
        if raw_token == "sk_valid-token":
            return {
                "userId": "token-user",
                "displayName": "Token User",
                "email": "token-user@example.test",
                "avatarUrl": "",
                "oauthProvider": "api_token",
                "platformRoles": ["USER"],
                "tokenScopes": ["skill:read"],
            }
        return None

    app.state.auth_bearer_reader = bearer_reader
    client = TestClient(app)
    headers = {"Authorization": "Bearer sk_valid-token"}

    auth_me = client.get("/api/v1/auth/me", headers=headers)
    clawhub = client.get("/api/v1/whoami", headers=headers)
    cli = client.get("/api/cli/v1/auth/whoami", headers=headers)

    assert auth_me.status_code == 200
    assert auth_me.json()["data"]["userId"] == "token-user"
    assert auth_me.json()["data"]["oauthProvider"] == "api_token"
    assert clawhub.status_code == 200
    assert clawhub.json() == {"user": {"handle": "token-user", "displayName": "Token User", "image": ""}}
    assert cli.status_code == 200
    assert cli.json()["data"]["handle"] == "token-user"


def test_current_principal_routes_keep_mock_user_precedence_over_bearer() -> None:
    app = create_app()
    seen_mock_ids: list[str] = []
    seen_bearer_tokens: list[str] = []

    def mock_reader(user_id: str) -> dict[str, object] | None:
        seen_mock_ids.append(user_id)
        return {
            "userId": user_id,
            "displayName": "Mock User",
            "email": "",
            "avatarUrl": "",
            "oauthProvider": "mock",
            "platformRoles": ["USER"],
        }

    def bearer_reader(raw_token: str) -> dict[str, object] | None:
        seen_bearer_tokens.append(raw_token)
        return {
            "userId": "token-user",
            "displayName": "Token User",
            "email": "",
            "avatarUrl": "",
            "oauthProvider": "api_token",
            "platformRoles": ["USER"],
        }

    app.state.auth_me_reader = mock_reader
    app.state.auth_bearer_reader = bearer_reader
    client = TestClient(app)
    response = client.get(
        "/api/v1/auth/me",
        headers={"X-Mock-User-Id": "mock-user", "Authorization": "Bearer sk_valid-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["userId"] == "mock-user"
    assert seen_mock_ids == ["mock-user"]
    assert seen_bearer_tokens == []


def test_current_principal_routes_reject_bad_bearer_headers() -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda raw_token: None
    client = TestClient(app)

    assert client.get("/api/v1/auth/me", headers={"Authorization": "Token sk_valid"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer sk_missing"}).status_code == 401


def test_current_principal_routes_reject_bad_bearer_before_session_fallback() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: {
        "userId": "session-user",
        "displayName": "Session User",
        "email": "session-user@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }
    client = TestClient(app)
    login = client.post("/api/v1/auth/local/login", json={"username": "session-user", "password": "Abcd123!"})
    assert login.status_code == 200

    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "})

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
