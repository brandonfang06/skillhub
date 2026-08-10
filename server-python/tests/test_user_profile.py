from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.user_profile import (
    UserProfileError,
    get_user_profile,
    update_user_profile,
)


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
    def __init__(self, connection: "FakeProfileConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeProfileConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeProfileConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeContext:
        return FakeContext(self.connection)

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeProfileConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {
            "user-1": {
                "id": "user-1",
                "display_name": "Current Name",
                "email": "user-1@example.test",
                "avatar_url": "https://example.test/avatar.png",
                "status": "ACTIVE",
            }
        }
        self.change_requests: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.profile_review_recipients = ["user-admin", "super-admin"]
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(" ".join(sql.split()))
        normalized = self.statements[-1]
        if "FROM user_account" in normalized and "WHERE id = :user_id" in normalized:
            row = self.users.get(str(bound["user_id"]))
            if row and row.get("status") == "ACTIVE":
                return FakeResult([row.copy()])
            return FakeResult([])
        if "FROM profile_change_request" in normalized and "ORDER BY created_at DESC" in normalized:
            rows = [
                row.copy()
                for row in self.change_requests
                if row["user_id"] == bound["user_id"] and row["status"] in {"PENDING", "REJECTED"}
            ]
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            return FakeResult(rows[:1])
        if normalized.startswith("UPDATE profile_change_request SET status = :status"):
            for row in self.change_requests:
                if row["user_id"] == bound["user_id"] and row["status"] == "PENDING":
                    row["status"] = bound["status"]
            return FakeResult()
        if normalized.startswith("UPDATE user_account"):
            self.users[str(bound["user_id"])]["display_name"] = bound["display_name"]
            return FakeResult()
        if normalized.startswith("INSERT INTO profile_change_request"):
            request_id = len(self.change_requests) + 1
            changes = bound["changes"]
            old_values = bound["old_values"]
            self.change_requests.append(
                {
                    "id": request_id,
                    "user_id": bound["user_id"],
                    "changes": json.loads(changes) if isinstance(changes, str) else changes,
                    "old_values": json.loads(old_values) if isinstance(old_values, str) else old_values,
                    "status": bound["status"],
                    "machine_result": bound["machine_result"],
                    "machine_reason": bound["machine_reason"],
                    "review_comment": None,
                    "created_at": bound["created_at"],
                }
            )
            return FakeResult([{"id": request_id}])
        if "FROM user_role_binding" in normalized and "USER_ADMIN" in normalized:
            return FakeResult([{"user_id": user_id} for user_id in self.profile_review_recipients])
        if normalized.startswith("INSERT INTO notification"):
            notification_id = len(self.notifications) + 1
            row = {"id": notification_id, **bound}
            self.notifications.append(row)
            return FakeResult([row])
        if normalized.startswith("INSERT INTO audit_log"):
            self.audit_logs.append(dict(bound))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.anyio
async def test_get_user_profile_applies_pending_self_view_overlay_and_policies() -> None:
    connection = FakeProfileConnection()
    connection.change_requests.append(
        {
            "id": 1,
            "user_id": "user-1",
            "changes": {"displayName": "Pending Name", "avatarUrl": "https://example.test/pending.png"},
            "old_values": {"displayName": "Current Name"},
            "status": "PENDING",
            "review_comment": None,
            "created_at": datetime(2026, 6, 11, 9, 0),
        }
    )

    result = await get_user_profile(FakeEngine(connection), "user-1")

    assert result["displayName"] == "Pending Name"
    assert result["avatarUrl"] == "https://example.test/pending.png"
    assert result["email"] == "user-1@example.test"
    assert result["pendingChanges"]["status"] == "PENDING"
    assert list(result["fieldPolicies"]) == ["displayName", "email"]
    assert result["fieldPolicies"]["displayName"] == {"editable": True, "requiresReview": True}
    assert result["fieldPolicies"]["email"] == {"editable": False, "requiresReview": False}


@pytest.mark.anyio
async def test_get_user_profile_rejected_change_does_not_overlay_current_values() -> None:
    connection = FakeProfileConnection()
    connection.change_requests.append(
        {
            "id": 1,
            "user_id": "user-1",
            "changes": {"displayName": "Rejected Name"},
            "old_values": {"displayName": "Current Name"},
            "status": "REJECTED",
            "review_comment": "no",
            "created_at": datetime(2026, 6, 11, 9, 0),
        }
    )

    result = await get_user_profile(FakeEngine(connection), "user-1")

    assert result["displayName"] == "Current Name"
    assert result["pendingChanges"]["status"] == "REJECTED"


@pytest.mark.anyio
async def test_update_user_profile_default_human_review_queues_pending_request() -> None:
    connection = FakeProfileConnection()
    published: list[tuple[str, dict[str, Any]]] = []

    class FakeFanout:
        async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
            published.append((user_id, payload))

    result = await update_user_profile(
        FakeEngine(connection),
        user_id="user-1",
        payload={"displayName": "  New Name  "},
        request_id="req-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
        human_review=True,
        machine_review=True,
        now=datetime(2026, 6, 11, 10, 0),
        notification_fanout=FakeFanout(),
    )

    assert result == {"status": "PENDING_REVIEW", "message": "response.profile.pendingReview"}
    assert connection.users["user-1"]["display_name"] == "Current Name"
    assert connection.change_requests[-1]["status"] == "PENDING"
    assert connection.change_requests[-1]["machine_result"] == "PASS"
    assert connection.change_requests[-1]["changes"] == {"displayName": "New Name"}
    assert connection.change_requests[-1]["old_values"] == {"displayName": "Current Name"}
    assert [row["recipient_id"] for row in connection.notifications] == ["user-admin", "super-admin"]
    assert {row["event_type"] for row in connection.notifications} == {"PROFILE_REVIEW_SUBMITTED"}
    body = json.loads(connection.notifications[0]["body_json"])
    assert body == {"profileReviewId": 1, "submitterId": "user-1", "fields": ["displayName"]}
    assert published == [
        (
            "user-admin",
            {
                "id": 1,
                "category": "REVIEW",
                "eventType": "PROFILE_REVIEW_SUBMITTED",
                "title": "Profile review submitted",
                "bodyJson": connection.notifications[0]["body_json"],
                "entityType": "PROFILE_REVIEW",
                "entityId": 1,
                "createdAt": "2026-06-11T10:00:00Z",
            },
        ),
        (
            "super-admin",
            {
                "id": 2,
                "category": "REVIEW",
                "eventType": "PROFILE_REVIEW_SUBMITTED",
                "title": "Profile review submitted",
                "bodyJson": connection.notifications[1]["body_json"],
                "entityType": "PROFILE_REVIEW",
                "entityId": 1,
                "createdAt": "2026-06-11T10:00:00Z",
            },
        ),
    ]
    assert connection.audit_logs == []


@pytest.mark.anyio
async def test_update_user_profile_without_human_review_applies_and_writes_audit() -> None:
    connection = FakeProfileConnection()

    result = await update_user_profile(
        FakeEngine(connection),
        user_id="user-1",
        payload={"displayName": "Applied Name"},
        request_id="req-2",
        client_ip="127.0.0.2",
        user_agent="pytest",
        human_review=False,
        machine_review=False,
        now=datetime(2026, 6, 11, 10, 1),
    )

    assert result == {"status": "APPLIED", "message": "response.profile.updated"}
    assert connection.users["user-1"]["display_name"] == "Applied Name"
    assert connection.change_requests[-1]["status"] == "APPROVED"
    assert connection.change_requests[-1]["machine_result"] == "SKIPPED"
    assert connection.audit_logs[-1]["action"] == "PROFILE_UPDATE"
    assert json.loads(connection.audit_logs[-1]["detail_json"]) == {
        "changes": {"displayName": "Applied Name"},
        "oldValues": {"displayName": "Current Name"},
    }


@pytest.mark.anyio
async def test_update_user_profile_validates_java_display_name_contract() -> None:
    engine = FakeEngine(FakeProfileConnection())

    with pytest.raises(UserProfileError, match="error.profile.noChanges"):
        await update_user_profile(engine, user_id="user-1", payload={}, request_id=None, client_ip=None, user_agent=None)
    with pytest.raises(UserProfileError, match="error.profile.displayName.length"):
        await update_user_profile(engine, user_id="user-1", payload={"displayName": "A"}, request_id=None, client_ip=None, user_agent=None)
    with pytest.raises(UserProfileError, match="error.profile.displayName.length"):
        await update_user_profile(engine, user_id="user-1", payload={"displayName": "a" * 33}, request_id=None, client_ip=None, user_agent=None)
    with pytest.raises(UserProfileError, match="error.profile.displayName.pattern"):
        await update_user_profile(
            engine,
            user_id="user-1",
            payload={"displayName": "<script>alert('xss')</script>"},
            request_id=None,
            client_ip=None,
            user_agent=None,
        )


def test_user_profile_routes_use_java_envelopes_and_auth_boundary() -> None:
    app = create_app()
    captured_meta: list[dict[str, str | None]] = []
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }
    app.state.user_profile_reader = lambda user_id: {
        "displayName": "User",
        "avatarUrl": "",
        "email": f"{user_id}@example.test",
        "pendingChanges": None,
        "fieldPolicies": {
            "displayName": {"editable": True, "requiresReview": True},
            "email": {"editable": False, "requiresReview": False},
        },
    }
    app.state.user_profile_writer = lambda user_id, payload, meta: captured_meta.append(meta) or {
        "status": "PENDING_REVIEW",
        "message": "response.profile.pendingReview",
    }

    client = TestClient(app)

    assert client.get("/api/v1/user/profile").status_code == 401

    get_response = client.get(
        "/api/v1/user/profile",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "profile-get"},
    )
    patch_response = client.patch(
        "/api/v1/user/profile",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "profile-patch"},
        json={"displayName": "New Name"},
    )

    assert get_response.status_code == 200
    assert get_response.json()["msg"] == "response.success.read"
    assert get_response.json()["requestId"] == "profile-get"
    assert get_response.json()["data"]["fieldPolicies"]["displayName"]["requiresReview"] is True
    assert patch_response.status_code == 200
    assert patch_response.json()["msg"] == "response.success.update"
    assert patch_response.json()["data"] == {
        "status": "PENDING_REVIEW",
        "message": "response.profile.pendingReview",
    }

    unsafe_patch_response = client.patch(
        "/api/v1/user/profile",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "x" * 65},
        json={"displayName": "New Name"},
    )
    assert unsafe_patch_response.status_code == 200
    assert captured_meta[-1]["request_id"] == unsafe_patch_response.json()["requestId"]
    assert captured_meta[-1]["request_id"] != "x" * 65
