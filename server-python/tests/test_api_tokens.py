from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.tokens import (
    ApiTokenError,
    create_api_token,
    list_api_tokens,
    revoke_api_token,
    sha256_token,
    update_api_token_expiration,
)
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self.rows = rows if rows is not None else ([row] if row is not None else [])

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return int(self.rows[0]["count"])


class FakeTransaction:
    def __init__(self, connection: "FakeTokenConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeTokenConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeTokenConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeTokenConnection:
    def __init__(self) -> None:
        self.next_id = 10
        self.tokens: list[dict[str, Any]] = [
            token_row(1, "user-1", "Old CLI", "sk_old12", "old-hash", ["skill:read"], "2026-06-10T08:00:00Z"),
            token_row(2, "user-1", "Deploy", "sk_deplo", "deploy-hash", ["skill:publish"], "2026-06-10T09:00:00Z"),
            token_row(3, "user-2", "Other", "sk_other", "other-hash", ["token:manage"], "2026-06-10T10:00:00Z"),
            token_row(4, "user-1", "Revoked", "sk_revo", "revoked-hash", [], "2026-06-10T11:00:00Z", revoked=True),
        ]
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.params.append(bound)
        if "SELECT id" in sql and "FROM api_token" in sql and "LOWER(name)" in sql:
            row = self._find_active_by_name(str(bound["user_id"]), str(bound["name"]))
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "UPDATE api_token" in sql and "revoked_at = :revoked_at" in sql:
            for row in self.tokens:
                if int(row["id"]) == int(bound["token_id"]):
                    row["revoked_at"] = bound["revoked_at"]
            return FakeResult()
        if "INSERT INTO api_token" in sql:
            row = {
                "id": self.next_id,
                "subject_type": "USER",
                "subject_id": bound["user_id"],
                "user_id": bound["user_id"],
                "name": bound["name"],
                "token_prefix": bound["token_prefix"],
                "token_hash": bound["token_hash"],
                "scope_json": __import__("json").loads(bound["scope_json"]),
                "expires_at": bound["expires_at"],
                "last_used_at": None,
                "revoked_at": None,
                "created_at": datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
            }
            self.next_id += 1
            self.tokens.append(row)
            return FakeResult(row=row.copy())
        if "COUNT(*) AS count" in sql and "FROM api_token" in sql:
            return FakeResult(row={"count": len(self._active_user_rows(str(bound["user_id"])))})
        if "FROM api_token" in sql and "ORDER BY created_at DESC" in sql:
            rows = self._active_user_rows(str(bound["user_id"]))
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            offset = int(bound.get("offset", 0))
            limit = int(bound.get("limit", len(rows)))
            return FakeResult(rows=[row.copy() for row in rows[offset : offset + limit]])
        if "FROM api_token" in sql and "WHERE id = :token_id" in sql:
            row = next((row for row in self.tokens if int(row["id"]) == int(bound["token_id"])), None)
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "UPDATE api_token" in sql and "expires_at = :expires_at" in sql:
            row = next(row for row in self.tokens if int(row["id"]) == int(bound["token_id"]))
            row["expires_at"] = bound["expires_at"]
            return FakeResult(row=row.copy())
        raise AssertionError(f"unexpected SQL: {sql}")

    def _find_active_by_name(self, user_id: str, name: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self.tokens
                if row["user_id"] == user_id and row["revoked_at"] is None and row["name"].lower() == name.lower()
            ),
            None,
        )

    def _active_user_rows(self, user_id: str) -> list[dict[str, Any]]:
        return [row for row in self.tokens if row["user_id"] == user_id and row["revoked_at"] is None]


def token_row(
    token_id: int,
    user_id: str,
    name: str,
    prefix: str,
    token_hash: str,
    scopes: list[str],
    created_at: str,
    *,
    revoked: bool = False,
) -> dict[str, Any]:
    return {
        "id": token_id,
        "subject_type": "USER",
        "subject_id": user_id,
        "user_id": user_id,
        "name": name,
        "token_prefix": prefix,
        "token_hash": token_hash,
        "scope_json": scopes,
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": datetime(2026, 6, 10, 12, 0, tzinfo=UTC) if revoked else None,
        "created_at": datetime.fromisoformat(created_at.replace("Z", "+00:00")),
    }


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


@pytest.mark.anyio
async def test_create_api_token_rotates_active_same_name_and_stores_hash_only() -> None:
    connection = FakeTokenConnection()

    response = await create_api_token(
        FakeEngine(connection),
        user_id="user-1",
        name="  Old CLI  ",
        scopes=None,
        expires_at="2026-06-11T12:00:00",
        token_generator=lambda: "sk_rawtokenfixture",
    )

    assert response["token"] == "sk_rawtokenfixture"
    assert response["id"] == 10
    assert response["name"] == "Old CLI"
    assert response["tokenPrefix"] == "sk_rawto"
    assert response["expiresAt"] == "2026-06-11T12:00:00Z"
    assert connection.tokens[0]["revoked_at"] is not None
    inserted = connection.tokens[-1]
    assert inserted["token_hash"] == sha256_token("sk_rawtokenfixture")
    assert inserted["token_hash"] != "sk_rawtokenfixture"
    assert inserted["scope_json"] == ["skill:read", "skill:publish"]


@pytest.mark.anyio
async def test_create_api_token_validates_java_name_and_expiration_rules() -> None:
    connection = FakeTokenConnection()

    for name, error in [
        ("   ", "validation.token.name.notBlank"),
        ("a" * 65, "validation.token.name.size"),
    ]:
        with pytest.raises(ApiTokenError, match=error):
            await create_api_token(FakeEngine(connection), user_id="user-1", name=name)

    with pytest.raises(ApiTokenError, match="validation.token.expiresAt.invalid"):
        await create_api_token(FakeEngine(connection), user_id="user-1", name="cli", expires_at="not-a-date")

    with pytest.raises(ApiTokenError, match="validation.token.expiresAt.future"):
        await create_api_token(FakeEngine(connection), user_id="user-1", name="cli", expires_at="2000-01-01T00:00:00Z")


@pytest.mark.anyio
async def test_list_revoke_and_update_expiration_are_user_scoped() -> None:
    connection = FakeTokenConnection()

    listed = await list_api_tokens(FakeEngine(connection), user_id="user-1", page=-1, size=0)
    assert listed["total"] == 2
    assert listed["page"] == 0
    assert listed["size"] == 1
    assert listed["items"][0]["name"] == "Deploy"
    assert listed["items"][0]["expiresAt"] == ""

    await revoke_api_token(FakeEngine(connection), user_id="user-1", token_id=3)
    assert connection.tokens[2]["revoked_at"] is None
    await revoke_api_token(FakeEngine(connection), user_id="user-1", token_id=2)
    assert connection.tokens[1]["revoked_at"] is not None

    updated = await update_api_token_expiration(
        FakeEngine(connection),
        user_id="user-1",
        token_id=1,
        expires_at="2026-07-01T09:30",
    )
    assert updated["id"] == 1
    assert updated["expiresAt"] == "2026-07-01T09:30:00Z"

    with pytest.raises(ApiTokenError, match="error.token.notFound") as missing:
        await update_api_token_expiration(FakeEngine(connection), user_id="user-1", token_id=3, expires_at=None)
    assert missing.value.status_code == 404


def test_api_token_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.token_creator = lambda payload, user: {
        "token": "sk_raw",
        "id": 7,
        "name": payload["name"].strip(),
        "tokenPrefix": "sk_raw",
        "createdAt": "2026-06-10T12:00:00Z",
        "expiresAt": "",
    }
    app.state.token_lister = lambda payload, user: {"items": [], "total": 0, "page": payload["page"], "size": payload["size"]}
    app.state.token_revoker = lambda token_id, user: None
    app.state.token_expiration_updater = lambda token_id, payload, user: {
        "id": token_id,
        "name": "cli",
        "tokenPrefix": "sk_raw",
        "createdAt": "2026-06-10T12:00:00Z",
        "expiresAt": "2026-07-01T09:30:00Z",
        "lastUsedAt": "",
    }
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/tokens",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "token-create"},
        json={"name": " cli "},
    )
    assert create_response.status_code == 200
    assert create_response.json()["code"] == 0
    assert create_response.json()["data"]["token"] == "sk_raw"
    assert create_response.json()["requestId"] == "token-create"

    list_response = client.get("/api/v1/tokens?page=1&size=5", headers={"X-Mock-User-Id": "user-1"})
    assert list_response.status_code == 200
    assert list_response.json()["data"] == {"items": [], "total": 0, "page": 1, "size": 5}

    update_response = client.put(
        "/api/v1/tokens/7/expiration",
        headers={"X-Mock-User-Id": "user-1"},
        json={"expiresAt": "2026-07-01T09:30"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["expiresAt"] == "2026-07-01T09:30:00Z"

    revoke_response = client.delete("/api/v1/tokens/7", headers={"X-Mock-User-Id": "user-1"})
    assert revoke_response.status_code == 204
    assert revoke_response.content == b""

    missing_auth = client.get("/api/v1/tokens")
    assert missing_auth.status_code == 401
    assert missing_auth.json()["detail"] == "error.auth.required"
