from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.device import (
    DEVICE_CLAIM_PREFIX,
    DEVICE_CODE_PREFIX,
    USER_CODE_PREFIX,
    DeviceAuthError,
    authorize_device_code,
    generate_device_code,
    poll_device_token,
)
from app.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ttl_seconds
        return True

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.ttls.pop(key, None)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeContext:
    def __init__(self, connection: "FakeTokenConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeTokenConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeTokenConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeTokenConnection:
    def __init__(self) -> None:
        self.next_id = 10
        self.tokens: list[dict[str, Any]] = [
            {
                "id": 1,
                "user_id": "user-1",
                "name": "CLI Device Flow",
                "token_prefix": "sk_old12",
                "token_hash": "old-hash",
                "scope_json": ["skill:read"],
                "revoked_at": None,
            }
        ]

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        bound = params or {}
        if sql.startswith("SELECT id FROM api_token"):
            row = next(
                (
                    row
                    for row in self.tokens
                    if row["user_id"] == bound["user_id"]
                    and row["revoked_at"] is None
                    and row["name"].lower() == str(bound["name"]).lower()
                ),
                None,
            )
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("UPDATE api_token SET revoked_at"):
            for row in self.tokens:
                if row["id"] == bound["token_id"]:
                    row["revoked_at"] = bound["revoked_at"]
            return FakeResult()
        if sql.startswith("INSERT INTO api_token"):
            row = {
                "id": self.next_id,
                "user_id": bound["user_id"],
                "name": bound["name"],
                "token_prefix": bound["token_prefix"],
                "token_hash": bound["token_hash"],
                "scope_json": json.loads(bound["scope_json"]),
                "expires_at": bound["expires_at"],
                "created_at": datetime(2026, 6, 11, 9, 0, tzinfo=UTC),
                "revoked_at": None,
            }
            self.next_id += 1
            self.tokens.append(row)
            return FakeResult([row.copy()])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeAuditConnection:
    def __init__(self) -> None:
        self.audit_logs: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        bound = params or {}
        if sql.startswith("INSERT INTO audit_log"):
            self.audit_logs.append(dict(bound))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def read_device_data(redis: FakeRedis, device_code: str) -> dict[str, Any]:
    raw = redis.values[f"{DEVICE_CODE_PREFIX}{device_code}"]
    return json.loads(raw)


@pytest.mark.anyio
async def test_generate_device_code_stores_pending_state_with_java_shape() -> None:
    redis = FakeRedis()

    response = await generate_device_code(
        redis,
        device_code_generator=lambda: "device-code-1",
        user_code_generator=lambda: "ABCD-2345",
        verification_uri="/cli/auth",
    )

    assert response == {
        "deviceCode": "device-code-1",
        "userCode": "ABCD-2345",
        "verificationUri": "/cli/auth",
        "expiresIn": 900,
        "interval": 5,
    }
    assert read_device_data(redis, "device-code-1") == {
        "deviceCode": "device-code-1",
        "userCode": "ABCD-2345",
        "status": "PENDING",
        "userId": None,
    }
    assert redis.values[f"{USER_CODE_PREFIX}ABCD-2345"] == "device-code-1"
    assert redis.ttls[f"{DEVICE_CODE_PREFIX}device-code-1"] == 900
    assert redis.ttls[f"{USER_CODE_PREFIX}ABCD-2345"] == 900


@pytest.mark.anyio
async def test_authorize_device_code_updates_pending_and_is_idempotent_for_same_user() -> None:
    redis = FakeRedis()
    await generate_device_code(redis, device_code_generator=lambda: "device-code-1", user_code_generator=lambda: "ABCD-2345")

    await authorize_device_code(redis, user_code="ABCD-2345", user_id="user-1")
    await authorize_device_code(redis, user_code="ABCD-2345", user_id="user-1")

    data = read_device_data(redis, "device-code-1")
    assert data["status"] == "AUTHORIZED"
    assert data["userId"] == "user-1"


@pytest.mark.anyio
async def test_authorize_device_code_matches_java_error_cases() -> None:
    redis = FakeRedis()

    with pytest.raises(DeviceAuthError, match="error.deviceAuth.userCode.invalid"):
        await authorize_device_code(redis, user_code="BAD-CODE", user_id="user-1")

    await generate_device_code(redis, device_code_generator=lambda: "device-code-1", user_code_generator=lambda: "ABCD-2345")
    await redis.delete(f"{DEVICE_CODE_PREFIX}device-code-1")
    with pytest.raises(DeviceAuthError, match="error.deviceAuth.deviceCode.expired"):
        await authorize_device_code(redis, user_code="ABCD-2345", user_id="user-1")

    await redis.set(
        f"{DEVICE_CODE_PREFIX}device-code-2",
        json.dumps({"deviceCode": "device-code-2", "userCode": "WXYZ-6789", "status": "AUTHORIZED", "userId": "user-1"}),
        900,
    )
    await redis.set(f"{USER_CODE_PREFIX}WXYZ-6789", "device-code-2", 900)
    with pytest.raises(DeviceAuthError, match="error.deviceAuth.deviceCode.alreadyAuthorized"):
        await authorize_device_code(redis, user_code="WXYZ-6789", user_id="user-2")


@pytest.mark.anyio
async def test_poll_device_token_returns_pending_then_redeems_once_and_rotates_cli_token() -> None:
    redis = FakeRedis()
    connection = FakeTokenConnection()
    await generate_device_code(redis, device_code_generator=lambda: "device-code-1", user_code_generator=lambda: "ABCD-2345")

    pending = await poll_device_token(redis, FakeEngine(connection), device_code="device-code-1")
    assert pending == {"accessToken": None, "tokenType": None, "error": "authorization_pending"}

    await authorize_device_code(redis, user_code="ABCD-2345", user_id="user-1")
    success = await poll_device_token(
        redis,
        FakeEngine(connection),
        device_code="device-code-1",
        token_generator=lambda: "sk_new-token",
    )

    assert success == {"accessToken": "sk_new-token", "tokenType": "Bearer", "error": None}
    assert connection.tokens[0]["revoked_at"] is not None
    assert connection.tokens[-1]["name"] == "CLI Device Flow"
    assert connection.tokens[-1]["scope_json"] == ["skill:read", "skill:publish"]
    assert read_device_data(redis, "device-code-1")["status"] == "USED"
    assert redis.ttls[f"{DEVICE_CODE_PREFIX}device-code-1"] == 60
    assert f"{USER_CODE_PREFIX}ABCD-2345" in redis.deleted

    with pytest.raises(DeviceAuthError, match="error.deviceAuth.deviceCode.used"):
        await poll_device_token(redis, FakeEngine(connection), device_code="device-code-1")


def test_device_auth_routes_use_java_envelopes_and_mock_user_auth() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }
    app.state.device_code_generator = lambda: {
        "deviceCode": "device-code-1",
        "userCode": "ABCD-2345",
        "verificationUri": "/cli/auth",
        "expiresIn": 900,
        "interval": 5,
    }
    authorized: list[tuple[str, dict[str, Any]]] = []
    audit_logs: list[dict[str, Any]] = []
    app.state.device_code_authorizer = lambda user_id, payload, request: authorized.append((user_id, payload))
    app.state.device_authorize_audit_writer = lambda user_id, payload, request: audit_logs.append((user_id, payload))
    app.state.device_token_poller = lambda payload: {"accessToken": None, "tokenType": None, "error": "authorization_pending"}

    with TestClient(app) as client:
        code_response = client.post("/api/v1/auth/device/code")
        authorize_response = client.post(
            "/api/v1/device/authorize",
            headers={"X-Mock-User-Id": "user-1"},
            json={"userCode": "ABCD-2345"},
        )
        token_response = client.post("/api/v1/auth/device/token", json={"deviceCode": "device-code-1"})
        missing_auth = client.post("/api/v1/device/authorize", json={"userCode": "ABCD-2345"})

    assert code_response.status_code == 200
    assert code_response.json()["msg"] == "response.success.created"
    assert code_response.json()["data"]["userCode"] == "ABCD-2345"
    assert authorize_response.status_code == 200
    assert authorize_response.json()["msg"] == "response.success.updated"
    assert authorize_response.json()["data"] == {"message": "Device authorized successfully"}
    assert token_response.status_code == 200
    assert token_response.json()["msg"] == "response.success.read"
    assert token_response.json()["data"]["error"] == "authorization_pending"
    assert missing_auth.status_code == 401
    assert authorized == [("user-1", {"userCode": "ABCD-2345"})]
    assert audit_logs == [("user-1", {"userCode": "ABCD-2345"})]


@pytest.mark.anyio
async def test_record_device_authorize_audit_matches_java_fields() -> None:
    from app.api.device_auth import record_device_authorize_audit

    connection = FakeAuditConnection()

    await record_device_authorize_audit(
        FakeEngine(connection),
        actor_user_id="user-1",
        user_code="ABCD-2345",
        request_id="request-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert isinstance(connection.audit_logs[0].pop("created_at"), datetime)
    assert connection.audit_logs == [
        {
            "actor_user_id": "user-1",
            "action": "DEVICE_AUTHORIZE",
            "target_type": "DEVICE_CODE",
            "target_id": None,
            "request_id": "request-1",
            "client_ip": "127.0.0.1",
            "user_agent": "pytest",
            "detail_json": '{"userCode":"ABCD-2345"}',
        }
    ]
