from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.local import (
    LocalAuthError,
    change_local_password,
    login_local_user,
    register_local_user,
    validate_password_policy,
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
    def __init__(self, connection: "FakeLocalAuthConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeLocalAuthConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeLocalAuthConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeLocalAuthConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {
            "user-1": user_row("user-1", "Alice", "alice@example.test", "ACTIVE"),
            "disabled": user_row("disabled", "Disabled", "disabled@example.test", "DISABLED"),
            "pending": user_row("pending", "Pending", "pending@example.test", "PENDING"),
            "merged": user_row("merged", "Merged", "merged@example.test", "MERGED"),
        }
        self.credentials: dict[str, dict[str, Any]] = {
            "user-1": credential_row("user-1", "alice", "hash:Abcd123!"),
            "disabled": credential_row("disabled", "disabled", "hash:Abcd123!"),
            "pending": credential_row("pending", "pending", "hash:Abcd123!"),
            "merged": credential_row("merged", "merged", "hash:Abcd123!"),
        }
        self.roles: dict[str, list[str]] = {"user-1": ["SKILL_ADMIN"]}
        self.namespaces = {"global": {"id": 1, "slug": "global"}}
        self.namespace_members: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM local_credential" in sql and "LOWER(username)" in sql:
            username = str(bound["username"]).lower()
            row = next((row for row in self.credentials.values() if row["username"].lower() == username), None)
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "FROM user_account" in sql and "LOWER(email)" in sql:
            email = str(bound["email"]).lower()
            row = next((row for row in self.users.values() if str(row["email"]).lower() == email), None)
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "FROM user_account" in sql and "WHERE id = :user_id" in sql:
            row = self.users.get(str(bound["user_id"]))
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "FROM local_credential" in sql and "WHERE user_id = :user_id" in sql:
            row = self.credentials.get(str(bound["user_id"]))
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "JOIN role" in sql and "user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.roles.get(str(bound["user_id"]), [])])
        if "FROM namespace" in sql and "slug = 'global'" in sql:
            return FakeResult(row=self.namespaces["global"].copy())
        if "FROM namespace_member" in sql:
            row = next(
                (
                    member
                    for member in self.namespace_members
                    if member["namespace_id"] == bound["namespace_id"] and member["user_id"] == bound["user_id"]
                ),
                None,
            )
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "INSERT INTO user_account" in sql:
            self.users[str(bound["id"])] = user_row(str(bound["id"]), str(bound["display_name"]), bound["email"], "ACTIVE")
            return FakeResult()
        if "INSERT INTO local_credential" in sql:
            self.credentials[str(bound["user_id"])] = credential_row(
                str(bound["user_id"]),
                str(bound["username"]),
                str(bound["password_hash"]),
            )
            return FakeResult()
        if "INSERT INTO namespace_member" in sql:
            self.namespace_members.append(
                {
                    "namespace_id": bound["namespace_id"],
                    "user_id": bound["user_id"],
                    "role": bound["role"],
                }
            )
            return FakeResult()
        if "UPDATE local_credential" in sql and "failed_attempts = :failed_attempts" in sql:
            credential = self.credentials[str(bound["user_id"])]
            credential["failed_attempts"] = bound["failed_attempts"]
            credential["locked_until"] = bound["locked_until"]
            return FakeResult()
        if "UPDATE local_credential" in sql and "password_hash = :password_hash" in sql:
            credential = self.credentials[str(bound["user_id"])]
            credential["password_hash"] = bound["password_hash"]
            credential["failed_attempts"] = 0
            credential["locked_until"] = None
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def user_row(user_id: str, display_name: str, email: str | None, status: str) -> dict[str, Any]:
    return {"id": user_id, "display_name": display_name, "email": email, "avatar_url": None, "status": status}


def credential_row(user_id: str, username: str, password_hash: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "username": username,
        "password_hash": password_hash,
        "failed_attempts": 0,
        "locked_until": None,
    }


def fake_hash(password: str) -> str:
    return f"hash:{password}"


def fake_verify(password: str, hashed: str) -> bool:
    return hashed == f"hash:{password}"


@pytest.mark.anyio
async def test_register_creates_active_user_credential_and_global_membership() -> None:
    connection = FakeLocalAuthConnection()

    principal = await register_local_user(
        FakeEngine(connection),
        username="  New_User  ",
        password="Abcd123!",
        email="  New@Example.Test  ",
        user_id_factory=lambda: "usr_test",
        password_hasher=fake_hash,
    )

    assert connection.users["usr_test"]["display_name"] == "new_user"
    assert connection.users["usr_test"]["email"] == "new@example.test"
    assert connection.credentials["usr_test"]["username"] == "new_user"
    assert connection.credentials["usr_test"]["password_hash"] == "hash:Abcd123!"
    assert connection.namespace_members == [{"namespace_id": 1, "user_id": "usr_test", "role": "MEMBER"}]
    assert principal == {
        "userId": "usr_test",
        "displayName": "new_user",
        "email": "new@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }


@pytest.mark.anyio
async def test_register_rejects_duplicate_username_email_and_weak_password() -> None:
    connection = FakeLocalAuthConnection()

    with pytest.raises(LocalAuthError, match="error.auth.local.username.exists"):
        await register_local_user(FakeEngine(connection), username="ALICE", password="Abcd123!", email="new@example.test")

    with pytest.raises(LocalAuthError, match="error.auth.local.email.exists"):
        await register_local_user(FakeEngine(connection), username="new_user", password="Abcd123!", email="ALICE@example.test")

    with pytest.raises(LocalAuthError, match="error.auth.local.password.tooWeak"):
        await register_local_user(FakeEngine(connection), username="new_user", password="aaaaaaaa", email="new@example.test")

    with pytest.raises(LocalAuthError, match="error.auth.local.username.invalid"):
        await register_local_user(FakeEngine(connection), username="ab", password="Abcd123!", email="new@example.test")


@pytest.mark.anyio
async def test_login_resets_failures_and_returns_local_principal() -> None:
    connection = FakeLocalAuthConnection()
    connection.credentials["user-1"]["failed_attempts"] = 3
    connection.credentials["user-1"]["locked_until"] = datetime.now(UTC) - timedelta(minutes=1)

    principal = await login_local_user(
        FakeEngine(connection),
        username=" Alice ",
        password="Abcd123!",
        password_verifier=fake_verify,
    )

    credential = connection.credentials["user-1"]
    assert credential["failed_attempts"] == 0
    assert credential["locked_until"] is None
    assert principal["oauthProvider"] == "local"
    assert principal["platformRoles"] == ["SKILL_ADMIN"]


@pytest.mark.anyio
async def test_login_rejects_bad_password_and_locks_after_fifth_failure() -> None:
    connection = FakeLocalAuthConnection()
    connection.credentials["user-1"]["failed_attempts"] = 4

    with pytest.raises(LocalAuthError, match="error.auth.local.invalidCredentials"):
        await login_local_user(FakeEngine(connection), username="alice", password="wrong", password_verifier=fake_verify)

    credential = connection.credentials["user-1"]
    assert credential["failed_attempts"] == 5
    assert credential["locked_until"] is not None

    with pytest.raises(LocalAuthError, match="error.auth.local.locked"):
        await login_local_user(FakeEngine(connection), username="alice", password="Abcd123!", password_verifier=fake_verify)


@pytest.mark.anyio
async def test_login_rejects_non_active_accounts_with_java_keys() -> None:
    connection = FakeLocalAuthConnection()

    with pytest.raises(LocalAuthError, match="error.auth.local.accountDisabled"):
        await login_local_user(FakeEngine(connection), username="disabled", password="Abcd123!", password_verifier=fake_verify)
    with pytest.raises(LocalAuthError, match="error.auth.local.accountPending"):
        await login_local_user(FakeEngine(connection), username="pending", password="Abcd123!", password_verifier=fake_verify)
    with pytest.raises(LocalAuthError, match="error.auth.local.accountMerged"):
        await login_local_user(FakeEngine(connection), username="merged", password="Abcd123!", password_verifier=fake_verify)


@pytest.mark.anyio
async def test_change_password_updates_hash_and_resets_lock_state() -> None:
    connection = FakeLocalAuthConnection()
    connection.credentials["user-1"]["failed_attempts"] = 5
    connection.credentials["user-1"]["locked_until"] = datetime.now(UTC) + timedelta(minutes=15)

    await change_local_password(
        FakeEngine(connection),
        user_id="user-1",
        current_password="Abcd123!",
        new_password="Newpass123!",
        password_verifier=fake_verify,
        password_hasher=fake_hash,
    )

    credential = connection.credentials["user-1"]
    assert credential["password_hash"] == "hash:Newpass123!"
    assert credential["failed_attempts"] == 0
    assert credential["locked_until"] is None

    with pytest.raises(LocalAuthError, match="error.auth.local.invalidCredentials"):
        await change_local_password(
            FakeEngine(connection),
            user_id="user-1",
            current_password="wrong",
            new_password="Another123!",
            password_verifier=fake_verify,
        )

    with pytest.raises(LocalAuthError, match="error.auth.local.invalidCredentials"):
        await change_local_password(
            FakeEngine(connection),
            user_id="user-1",
            current_password="wrong",
            new_password="aaaaaaaa",
            password_verifier=fake_verify,
        )


def test_password_policy_matches_java_character_category_rules() -> None:
    assert validate_password_policy("Abcd123!") == "Abcd123!"
    with pytest.raises(LocalAuthError, match="error.auth.local.password.tooShort"):
        validate_password_policy("Ab1!")
    with pytest.raises(LocalAuthError, match="error.auth.local.password.tooLong"):
        validate_password_policy("A1!" + "a" * 126)
    with pytest.raises(LocalAuthError, match="error.auth.local.password.tooWeak"):
        validate_password_policy("aaaaaaaa")


def test_local_auth_core_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    app.state.local_auth_registrar = lambda payload: {
        "userId": "usr_route",
        "displayName": "route",
        "email": "route@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }
    app.state.local_auth_login = lambda payload: {
        "userId": "usr_route",
        "displayName": "route",
        "email": "route@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }
    app.state.local_auth_password_changer = lambda user_id, payload: None
    client = TestClient(app)

    register = client.post(
        "/api/v1/auth/local/register",
        json={"username": "route", "password": "Abcd123!", "email": "route@example.test"},
    )
    assert register.status_code == 200
    assert register.json()["code"] == 0
    assert register.json()["data"]["oauthProvider"] == "local"

    login = client.post("/api/v1/auth/local/login", json={"username": "route", "password": "Abcd123!"})
    assert login.status_code == 200
    assert login.json()["code"] == 0
    assert login.json()["data"]["userId"] == "usr_route"

    missing_auth = client.post(
        "/api/v1/auth/local/change-password",
        json={"currentPassword": "Abcd123!", "newPassword": "Newpass123!"},
    )
    assert missing_auth.status_code == 401

    changed = client.post(
        "/api/v1/auth/local/change-password",
        headers={"X-Mock-User-Id": "usr_route"},
        json={"currentPassword": "Abcd123!", "newPassword": "Newpass123!"},
    )
    assert changed.status_code == 200
    assert changed.json()["code"] == 0
    assert changed.json()["data"] is None
