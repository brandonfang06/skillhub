from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.password_reset import (
    PasswordResetError,
    confirm_password_reset,
    hash_bcrypt_value,
    request_password_reset,
    verify_bcrypt_value,
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


class FakeTransaction:
    def __init__(self, connection: "FakePasswordResetConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakePasswordResetConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakePasswordResetConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakePasswordResetConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {
            "user-1": user_row("user-1", "alice@example.test", "ACTIVE"),
            "user-2": user_row("user-2", "disabled@example.test", "DISABLED"),
            "user-3": user_row("user-3", "missing-credential@example.test", "ACTIVE"),
            "builtin-skill-publisher": user_row(
                "builtin-skill-publisher",
                "builtin-skill-publisher@system.invalid",
                "ACTIVE",
                system_account=True,
            ),
        }
        self.credentials: dict[str, dict[str, Any]] = {
            "user-1": {
                "user_id": "user-1",
                "username": "alice",
                "password_hash": "old-hash",
                "failed_attempts": 4,
                "locked_until": datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
            },
            "builtin-skill-publisher": {
                "user_id": "builtin-skill-publisher",
                "username": "builtin",
                "password_hash": "system-hash",
                "failed_attempts": 0,
                "locked_until": None,
            },
        }
        self.reset_requests: list[dict[str, Any]] = [
            {
                "id": 1,
                "user_id": "user-1",
                "email": "alice@example.test",
                "code_hash": "$2b$12$oldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldoldold",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "consumed_at": None,
                "requested_by_admin": False,
                "requested_by_user_id": None,
            }
        ]
        self.next_reset_id = 2

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM user_account" in sql and "LOWER(email)" in sql:
            email = str(bound["email"]).lower()
            row = next((row for row in self.users.values() if row["email"].lower() == email), None)
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "FROM local_credential" in sql:
            user_id = str(bound["user_id"])
            row = self.credentials.get(user_id)
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "UPDATE password_reset_request" in sql and "SET consumed_at" in sql:
            for row in self.reset_requests:
                if row["user_id"] == bound["user_id"] and row["consumed_at"] is None:
                    row["consumed_at"] = bound["consumed_at"]
            return FakeResult()
        if "INSERT INTO password_reset_request" in sql:
            self.reset_requests.append(
                {
                    "id": self.next_reset_id,
                    "user_id": bound["user_id"],
                    "email": bound["email"],
                    "code_hash": bound["code_hash"],
                    "expires_at": bound["expires_at"],
                    "consumed_at": None,
                    "requested_by_admin": bound["requested_by_admin"],
                    "requested_by_user_id": bound["requested_by_user_id"],
                }
            )
            self.next_reset_id += 1
            return FakeResult()
        if "FROM password_reset_request" in sql:
            rows = [
                row.copy()
                for row in self.reset_requests
                if row["user_id"] == bound["user_id"] and row["consumed_at"] is None and row["expires_at"] > bound["now"]
            ]
            rows.sort(key=lambda row: row["id"], reverse=True)
            return FakeResult(rows=rows)
        if "UPDATE local_credential" in sql:
            credential = self.credentials[str(bound["user_id"])]
            credential["password_hash"] = bound["password_hash"]
            credential["failed_attempts"] = 0
            credential["locked_until"] = None
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def user_row(user_id: str, email: str, status: str, *, system_account: bool = False) -> dict[str, Any]:
    return {"id": user_id, "email": email, "status": status, "system_account": system_account}


@pytest.mark.anyio
async def test_request_password_reset_is_silent_for_unknown_or_ineligible_and_writes_for_eligible() -> None:
    connection = FakePasswordResetConnection()

    await request_password_reset(
        FakeEngine(connection),
        email="  Alice@Example.Test  ",
        code_generator=lambda: "123456",
        code_hasher=lambda code: f"hashed-{code}",
        sender=lambda email, code, is_admin: (_ for _ in ()).throw(RuntimeError("smtp down")),
    )

    assert connection.reset_requests[0]["consumed_at"] is not None
    inserted = connection.reset_requests[-1]
    assert inserted["email"] == "alice@example.test"
    assert inserted["code_hash"] == "hashed-123456"
    assert inserted["requested_by_admin"] is False
    assert inserted["requested_by_user_id"] is None

    before = len(connection.reset_requests)
    await request_password_reset(FakeEngine(connection), email="ghost@example.test")
    await request_password_reset(FakeEngine(connection), email="disabled@example.test")
    await request_password_reset(FakeEngine(connection), email="missing-credential@example.test")
    assert len(connection.reset_requests) == before

    with pytest.raises(PasswordResetError, match="validation.auth.password.reset.email.invalid"):
        await request_password_reset(FakeEngine(connection), email="alice")


@pytest.mark.anyio
async def test_request_password_reset_is_silent_for_system_accounts() -> None:
    connection = FakePasswordResetConnection()
    before = len(connection.reset_requests)

    await request_password_reset(
        FakeEngine(connection),
        email="builtin-skill-publisher@system.invalid",
        code_generator=lambda: "123456",
        code_hasher=lambda code: f"hashed-{code}",
    )

    assert len(connection.reset_requests) == before
    assert all(row["user_id"] != "builtin-skill-publisher" for row in connection.reset_requests)


@pytest.mark.anyio
async def test_confirm_password_reset_updates_credential_and_consumes_pending_requests() -> None:
    connection = FakePasswordResetConnection()
    connection.reset_requests.append(
        {
            "id": 5,
            "user_id": "user-1",
            "email": "alice@example.test",
            "code_hash": "$2b$12$ABCDEFGHIJKLMNOPQRSTUOpxAF9ozgUdI5C/xUa4f.iVO/V9O3x0y",
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
            "consumed_at": None,
            "requested_by_admin": False,
            "requested_by_user_id": None,
        }
    )

    await confirm_password_reset(
        FakeEngine(connection),
        email="alice@example.test",
        code="123456",
        new_password="Abcd123!",
        code_verifier=lambda code, code_hash: code == "123456" and code_hash.startswith("$2b$12$ABCDEFGHIJKLMNOP"),
        password_hasher=lambda password: f"new-hash-{password}",
    )

    credential = connection.credentials["user-1"]
    assert credential["password_hash"] == "new-hash-Abcd123!"
    assert credential["failed_attempts"] == 0
    assert credential["locked_until"] is None
    assert all(row["consumed_at"] is not None for row in connection.reset_requests if row["user_id"] == "user-1")


@pytest.mark.anyio
async def test_confirm_password_reset_matches_java_error_cases() -> None:
    connection = FakePasswordResetConnection()

    with pytest.raises(PasswordResetError, match="validation.auth.password.reset.code.invalid"):
        await confirm_password_reset(FakeEngine(connection), email="alice@example.test", code="12345", new_password="Abcd123!")

    with pytest.raises(PasswordResetError, match="error.auth.password.reset.invalid.code"):
        await confirm_password_reset(FakeEngine(connection), email="alice@example.test", code="999999", new_password="Abcd123!")

    with pytest.raises(PasswordResetError, match="error.auth.local.password.tooWeak"):
        await confirm_password_reset(
            FakeEngine(connection),
            email="alice@example.test",
            code="123456",
            new_password="aaaaaaaa",
            code_verifier=lambda code, code_hash: True,
        )

    with pytest.raises(PasswordResetError, match="error.auth.password.reset.no.credential"):
        connection.reset_requests.append(
            {
                "id": 6,
                "user_id": "user-3",
                "email": "missing-credential@example.test",
                "code_hash": "code-for-missing-credential",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "consumed_at": None,
                "requested_by_admin": False,
                "requested_by_user_id": None,
            }
        )
        await confirm_password_reset(
            FakeEngine(connection),
            email="missing-credential@example.test",
            code="123456",
            new_password="Abcd123!",
            code_verifier=lambda code, code_hash: True,
        )


def test_verify_bcrypt_value_accepts_java_compatible_hashes() -> None:
    hashed_value = hash_bcrypt_value("123456")

    assert verify_bcrypt_value("123456", hashed_value)
    assert not verify_bcrypt_value("654321", hashed_value)


def test_local_password_reset_routes_use_java_envelopes() -> None:
    app = create_app()
    app.state.local_password_reset_requester = lambda payload: None
    app.state.local_password_reset_confirmer = lambda payload: None
    client = TestClient(app)

    request_response = client.post("/api/v1/auth/local/password-reset/request", json={"email": "alice@example.test"})
    assert request_response.status_code == 200
    assert request_response.json()["code"] == 0
    assert request_response.json()["data"] is None

    confirm_response = client.post(
        "/api/v1/auth/local/password-reset/confirm",
        json={"email": "alice@example.test", "code": "123456", "newPassword": "Abcd123!"},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["code"] == 0
    assert confirm_response.json()["data"] is None

    invalid_response = client.post("/api/v1/auth/local/password-reset/request", json={"email": "alice"})
    assert invalid_response.status_code == 400
