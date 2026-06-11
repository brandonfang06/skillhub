from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.account_merge import (
    AccountMergeError,
    confirm_account_merge,
    initiate_account_merge,
    verify_account_merge,
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
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeContext:
    def __init__(self, connection: "FakeAccountMergeConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeAccountMergeConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeAccountMergeConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeContext:
        return FakeContext(self.connection)

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeAccountMergeConnection:
    def __init__(self) -> None:
        self.next_merge_id = 10
        self.next_role_binding_id = 4
        self.users: dict[str, dict[str, Any]] = {
            "usr_primary": user("usr_primary", "Primary", ""),
            "usr_secondary": user("usr_secondary", "Secondary", "secondary@example.test"),
            "usr_disabled": user("usr_disabled", "Disabled", "", status="DISABLED"),
        }
        self.local_credentials: list[dict[str, Any]] = [
            {"id": 1, "user_id": "usr_secondary", "username": "secondary", "password_hash": "hash-secondary"},
        ]
        self.identity_bindings: list[dict[str, Any]] = [
            {
                "id": 1,
                "user_id": "usr_secondary",
                "provider_code": "github",
                "subject": "gh-2",
                "login_name": "secondary-gh",
            }
        ]
        self.api_tokens: list[dict[str, Any]] = [
            {"id": 1, "user_id": "usr_secondary", "subject_type": "USER", "subject_id": "usr_secondary"},
            {"id": 2, "user_id": "usr_secondary", "subject_type": "NAMESPACE", "subject_id": "20"},
        ]
        self.roles: dict[int, str] = {1: "USER", 2: "AUDITOR"}
        self.user_role_bindings: list[dict[str, Any]] = [
            {"id": 1, "user_id": "usr_primary", "role_id": 1},
            {"id": 2, "user_id": "usr_secondary", "role_id": 1},
            {"id": 3, "user_id": "usr_secondary", "role_id": 2},
        ]
        self.namespace_members: list[dict[str, Any]] = [
            {"id": 1, "namespace_id": 20, "user_id": "usr_primary", "role": "MEMBER"},
            {"id": 2, "namespace_id": 20, "user_id": "usr_secondary", "role": "OWNER"},
            {"id": 3, "namespace_id": 21, "user_id": "usr_secondary", "role": "ADMIN"},
        ]
        self.merge_requests: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        bound = params or {}

        if sql.startswith("SELECT id, display_name, email, avatar_url, status FROM user_account"):
            row = self.users.get(str(bound["user_id"]))
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("SELECT user_id FROM local_credential WHERE LOWER(username)"):
            username = str(bound["username"]).lower()
            row = next((row for row in self.local_credentials if row["username"].lower() == username), None)
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("SELECT user_id FROM identity_binding WHERE provider_code"):
            row = next(
                (
                    row
                    for row in self.identity_bindings
                    if row["provider_code"] == bound["provider_code"] and row["subject"] == bound["subject"]
                ),
                None,
            )
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("SELECT id FROM account_merge_request WHERE secondary_user_id"):
            row = next(
                (
                    row
                    for row in self.merge_requests
                    if row["secondary_user_id"] == bound["secondary_user_id"] and row["status"] == "PENDING"
                ),
                None,
            )
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("SELECT id, user_id, username, password_hash FROM local_credential WHERE user_id"):
            row = next((row for row in self.local_credentials if row["user_id"] == bound["user_id"]), None)
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("INSERT INTO account_merge_request"):
            row = {
                "id": self.next_merge_id,
                "primary_user_id": bound["primary_user_id"],
                "secondary_user_id": bound["secondary_user_id"],
                "status": "PENDING",
                "verification_token": bound["verification_token"],
                "token_expires_at": bound["token_expires_at"],
                "completed_at": None,
                "created_at": bound["created_at"],
            }
            self.next_merge_id += 1
            self.merge_requests.append(row)
            return FakeResult([row.copy()])
        if sql.startswith("SELECT id, primary_user_id, secondary_user_id, status, verification_token"):
            row = next(
                (
                    row
                    for row in self.merge_requests
                    if int(row["id"]) == int(bound["merge_request_id"])
                    and row["primary_user_id"] == bound["primary_user_id"]
                ),
                None,
            )
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("UPDATE account_merge_request SET status = 'VERIFIED'"):
            for row in self.merge_requests:
                if int(row["id"]) == int(bound["merge_request_id"]):
                    row["status"] = "VERIFIED"
            return FakeResult()
        if sql.startswith("SELECT id, user_id, provider_code, subject, login_name FROM identity_binding"):
            return FakeResult([row.copy() for row in self.identity_bindings if row["user_id"] == bound["secondary_user_id"]])
        if sql.startswith("UPDATE identity_binding SET user_id"):
            for row in self.identity_bindings:
                if row["id"] == bound["binding_id"]:
                    row["user_id"] = bound["primary_user_id"]
            return FakeResult()
        if sql.startswith("SELECT id, subject_type, subject_id, user_id FROM api_token"):
            return FakeResult([row.copy() for row in self.api_tokens if row["user_id"] == bound["secondary_user_id"]])
        if sql.startswith("UPDATE api_token SET user_id"):
            for row in self.api_tokens:
                if row["id"] == bound["token_id"]:
                    row["user_id"] = bound["primary_user_id"]
                    if row["subject_type"] == "USER":
                        row["subject_id"] = bound["subject_id"]
            return FakeResult()
        if sql.startswith("SELECT urb.id, urb.user_id, urb.role_id, r.code FROM user_role_binding urb"):
            rows = [
                {**row, "code": self.roles[row["role_id"]]}
                for row in self.user_role_bindings
                if row["user_id"] == bound["user_id"]
            ]
            return FakeResult(rows)
        if sql.startswith("INSERT INTO user_role_binding"):
            self.user_role_bindings.append(
                {"id": self.next_role_binding_id, "user_id": bound["primary_user_id"], "role_id": bound["role_id"]}
            )
            self.next_role_binding_id += 1
            return FakeResult()
        if sql.startswith("DELETE FROM user_role_binding WHERE id"):
            self.user_role_bindings = [row for row in self.user_role_bindings if row["id"] != bound["binding_id"]]
            return FakeResult()
        if sql.startswith("SELECT id, namespace_id, user_id, role FROM namespace_member WHERE user_id"):
            return FakeResult([row.copy() for row in self.namespace_members if row["user_id"] == bound["user_id"]])
        if sql.startswith("SELECT id, namespace_id, user_id, role FROM namespace_member WHERE namespace_id"):
            row = next(
                (
                    row
                    for row in self.namespace_members
                    if row["namespace_id"] == bound["namespace_id"] and row["user_id"] == bound["primary_user_id"]
                ),
                None,
            )
            return FakeResult([row.copy()]) if row else FakeResult()
        if sql.startswith("UPDATE namespace_member SET role"):
            for row in self.namespace_members:
                if row["id"] == bound["member_id"]:
                    row["role"] = bound["role"]
            return FakeResult()
        if sql.startswith("DELETE FROM namespace_member WHERE namespace_id"):
            self.namespace_members = [
                row
                for row in self.namespace_members
                if not (row["namespace_id"] == bound["namespace_id"] and row["user_id"] == bound["secondary_user_id"])
            ]
            return FakeResult()
        if sql.startswith("UPDATE namespace_member SET user_id"):
            for row in self.namespace_members:
                if row["id"] == bound["member_id"]:
                    row["user_id"] = bound["primary_user_id"]
            return FakeResult()
        if sql.startswith("UPDATE local_credential SET user_id"):
            for row in self.local_credentials:
                if row["id"] == bound["credential_id"]:
                    row["user_id"] = bound["primary_user_id"]
            return FakeResult()
        if sql.startswith("UPDATE user_account SET email"):
            self.users[str(bound["primary_user_id"])]["email"] = bound["email"]
            return FakeResult()
        if sql.startswith("UPDATE user_account SET status = 'MERGED'"):
            row = self.users[str(bound["secondary_user_id"])]
            row["status"] = "MERGED"
            row["merged_to_user_id"] = bound["primary_user_id"]
            return FakeResult()
        if sql.startswith("UPDATE account_merge_request SET status = 'COMPLETED'"):
            for row in self.merge_requests:
                if int(row["id"]) == int(bound["merge_request_id"]):
                    row["status"] = "COMPLETED"
                    row["completed_at"] = bound["completed_at"]
                    row["verification_token"] = None
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def user(user_id: str, name: str, email: str, *, status: str = "ACTIVE") -> dict[str, Any]:
    return {
        "id": user_id,
        "display_name": name,
        "email": email,
        "avatar_url": "",
        "status": status,
        "merged_to_user_id": None,
    }


def fixed_now() -> datetime:
    return datetime(2026, 6, 11, 8, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_initiate_account_merge_creates_pending_request_with_raw_token_response() -> None:
    connection = FakeAccountMergeConnection()

    result = await initiate_account_merge(
        FakeEngine(connection),
        primary_user_id="usr_primary",
        secondary_identifier=" Secondary ",
        now_provider=fixed_now,
        token_generator=lambda: "raw-token",
        token_hasher=lambda raw: f"hashed-{raw}",
    )

    assert result == {
        "mergeRequestId": 10,
        "secondaryUserId": "usr_secondary",
        "verificationToken": "raw-token",
        "expiresAt": "2026-06-11T08:30:00Z",
    }
    assert connection.merge_requests[0]["verification_token"] == "hashed-raw-token"
    assert connection.merge_requests[0]["token_expires_at"] == fixed_now() + timedelta(minutes=30)


@pytest.mark.anyio
async def test_initiate_account_merge_matches_java_error_cases() -> None:
    connection = FakeAccountMergeConnection()

    with pytest.raises(AccountMergeError, match="error.auth.merge.identifierRequired"):
        await initiate_account_merge(FakeEngine(connection), primary_user_id="usr_primary", secondary_identifier=" ")

    with pytest.raises(AccountMergeError, match="error.auth.merge.identifierInvalid"):
        await initiate_account_merge(FakeEngine(connection), primary_user_id="usr_primary", secondary_identifier="github:")

    with pytest.raises(AccountMergeError, match="error.auth.merge.secondaryNotFound"):
        await initiate_account_merge(FakeEngine(connection), primary_user_id="usr_primary", secondary_identifier="missing")

    connection.local_credentials.append(
        {"id": 2, "user_id": "usr_primary", "username": "primary", "password_hash": "hash-primary"}
    )
    with pytest.raises(AccountMergeError) as exc_info:
        await initiate_account_merge(FakeEngine(connection), primary_user_id="usr_primary", secondary_identifier="secondary")
    assert exc_info.value.status_code == 409
    assert str(exc_info.value) == "error.auth.merge.localCredentialConflict"


@pytest.mark.anyio
async def test_verify_account_merge_marks_pending_request_verified() -> None:
    connection = FakeAccountMergeConnection()
    connection.merge_requests.append(
        {
            "id": 7,
            "primary_user_id": "usr_primary",
            "secondary_user_id": "usr_secondary",
            "status": "PENDING",
            "verification_token": "encoded-token",
            "token_expires_at": fixed_now() + timedelta(minutes=5),
            "completed_at": None,
            "created_at": fixed_now(),
        }
    )

    await verify_account_merge(
        FakeEngine(connection),
        primary_user_id="usr_primary",
        merge_request_id=7,
        verification_token="raw-token",
        now_provider=fixed_now,
        token_verifier=lambda raw, hashed: raw == "raw-token" and hashed == "encoded-token",
    )

    assert connection.merge_requests[0]["status"] == "VERIFIED"


@pytest.mark.anyio
async def test_verify_account_merge_rejects_invalid_or_expired_tokens() -> None:
    connection = FakeAccountMergeConnection()
    connection.merge_requests.append(
        {
            "id": 7,
            "primary_user_id": "usr_primary",
            "secondary_user_id": "usr_secondary",
            "status": "PENDING",
            "verification_token": "encoded-token",
            "token_expires_at": fixed_now() - timedelta(seconds=1),
            "completed_at": None,
            "created_at": fixed_now(),
        }
    )

    with pytest.raises(AccountMergeError, match="error.auth.merge.tokenExpired"):
        await verify_account_merge(
            FakeEngine(connection),
            primary_user_id="usr_primary",
            merge_request_id=7,
            verification_token="raw-token",
            now_provider=fixed_now,
        )

    connection.merge_requests[0]["token_expires_at"] = fixed_now() + timedelta(minutes=5)
    with pytest.raises(AccountMergeError) as exc_info:
        await verify_account_merge(
            FakeEngine(connection),
            primary_user_id="usr_primary",
            merge_request_id=7,
            verification_token="bad-token",
            now_provider=fixed_now,
            token_verifier=lambda raw, hashed: False,
        )
    assert exc_info.value.status_code == 401
    assert str(exc_info.value) == "error.auth.merge.invalidToken"


@pytest.mark.anyio
async def test_confirm_account_merge_moves_secondary_assets_and_completes_request() -> None:
    connection = FakeAccountMergeConnection()
    connection.merge_requests.append(
        {
            "id": 7,
            "primary_user_id": "usr_primary",
            "secondary_user_id": "usr_secondary",
            "status": "VERIFIED",
            "verification_token": "encoded-token",
            "token_expires_at": fixed_now() + timedelta(minutes=5),
            "completed_at": None,
            "created_at": fixed_now(),
        }
    )

    await confirm_account_merge(
        FakeEngine(connection),
        primary_user_id="usr_primary",
        merge_request_id=7,
        now_provider=fixed_now,
    )

    assert {row["user_id"] for row in connection.identity_bindings} == {"usr_primary"}
    user_tokens = [row for row in connection.api_tokens if row["subject_type"] == "USER"]
    assert user_tokens[0]["user_id"] == "usr_primary"
    assert user_tokens[0]["subject_id"] == "usr_primary"
    assert any(row["user_id"] == "usr_primary" and row["role_id"] == 2 for row in connection.user_role_bindings)
    assert not any(row["user_id"] == "usr_secondary" for row in connection.user_role_bindings)
    assert next(row for row in connection.namespace_members if row["namespace_id"] == 20)["role"] == "OWNER"
    assert not any(row["namespace_id"] == 20 and row["user_id"] == "usr_secondary" for row in connection.namespace_members)
    assert any(row["namespace_id"] == 21 and row["user_id"] == "usr_primary" for row in connection.namespace_members)
    assert next(row for row in connection.local_credentials if row["username"] == "secondary")["user_id"] == "usr_primary"
    assert connection.users["usr_primary"]["email"] == "secondary@example.test"
    assert connection.users["usr_secondary"]["status"] == "MERGED"
    assert connection.users["usr_secondary"]["merged_to_user_id"] == "usr_primary"
    assert connection.merge_requests[0]["status"] == "COMPLETED"
    assert connection.merge_requests[0]["verification_token"] is None
    assert connection.merge_requests[0]["completed_at"] == fixed_now()


def test_account_merge_routes_use_java_envelopes_and_mock_user_auth() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }
    app.state.account_merge_initiator = lambda user_id, payload: {
        "mergeRequestId": 1,
        "secondaryUserId": "usr_secondary",
        "verificationToken": "merge-token",
        "expiresAt": "2026-06-11T08:30:00Z",
    }
    verified: list[tuple[str, dict[str, Any]]] = []
    confirmed: list[tuple[str, dict[str, Any]]] = []
    app.state.account_merge_verifier = lambda user_id, payload: verified.append((user_id, payload))
    app.state.account_merge_confirmer = lambda user_id, payload: confirmed.append((user_id, payload))

    with TestClient(app) as client:
        initiate = client.post(
            "/api/v1/account/merge/initiate",
            headers={"X-Mock-User-Id": "usr_primary", "X-Request-Id": "merge-initiate"},
            json={"secondaryIdentifier": "secondary"},
        )
        verify = client.post(
            "/api/v1/account/merge/verify",
            headers={"X-Mock-User-Id": "usr_primary"},
            json={"mergeRequestId": 1, "verificationToken": "merge-token"},
        )
        confirm = client.post(
            "/api/v1/account/merge/confirm",
            headers={"X-Mock-User-Id": "usr_primary"},
            json={"mergeRequestId": 1},
        )
        missing = client.post("/api/v1/account/merge/initiate", json={"secondaryIdentifier": "secondary"})

    assert initiate.status_code == 200
    assert initiate.json()["msg"] == "response.success.created"
    assert initiate.json()["data"]["verificationToken"] == "merge-token"
    assert verify.status_code == 200
    assert verify.json()["msg"] == "response.success.updated"
    assert verify.json()["data"] == {"message": "Account merge verified"}
    assert confirm.status_code == 200
    assert confirm.json()["data"] == {"message": "Account merge completed"}
    assert verified == [("usr_primary", {"mergeRequestId": 1, "verificationToken": "merge-token"})]
    assert confirmed == [("usr_primary", {"mergeRequestId": 1})]
    assert missing.status_code == 401
    assert missing.json()["detail"] == "error.auth.required"
