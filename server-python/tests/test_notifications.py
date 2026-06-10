from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications.service import (
    NotificationError,
    build_notification_response,
    delete_read_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, *, scalar: Any = None, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self.scalar = scalar
        self.rows = rows or []
        self.rowcount = rowcount

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnect:
    def __init__(self, connection: "FakeNotificationConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeNotificationConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeTransaction(FakeConnect):
    pass


class FakeEngine:
    def __init__(self, connection: "FakeNotificationConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeNotificationConnection:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, total: int = 0, count: int = 0) -> None:
        self.rows = rows or []
        self.total = total
        self.count = count
        self.notification: dict[str, Any] | None = None
        self.updated = 0
        self.deleted = 0
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "COUNT(*)" in sql and "status = 'UNREAD'" in sql:
            return FakeResult(scalar=self.count)
        if "COUNT(*)" in sql:
            return FakeResult(scalar=self.total)
        if "SELECT id," in sql and "FROM notification" in sql and "LIMIT 1" in sql:
            return FakeResult(rows=[self.notification] if self.notification is not None else [])
        if "SELECT id," in sql and "FROM notification" in sql:
            return FakeResult(rows=self.rows)
        if "UPDATE notification" in sql and "RETURNING id" in sql:
            return FakeResult(rows=[self.notification] if self.notification is not None else [])
        if "UPDATE notification" in sql and "status = 'UNREAD'" in sql:
            return FakeResult(rowcount=self.updated)
        if "DELETE FROM notification" in sql:
            return FakeResult(rowcount=self.deleted)
        raise AssertionError(f"unexpected SQL: {sql}")


def notification_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 11,
        "recipient_id": "user-1",
        "category": "REVIEW",
        "event_type": "REVIEW_SUBMITTED",
        "title": "Review submitted",
        "body_json": '{"namespace":"team-a","slug":"demo"}',
        "entity_type": "SKILL",
        "entity_id": 77,
        "status": "UNREAD",
        "created_at": datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
        "read_at": None,
    }
    data.update(overrides)
    return data


def test_build_notification_response_matches_java_target_resolution() -> None:
    assert build_notification_response(notification_row()) == {
        "id": 11,
        "category": "REVIEW",
        "eventType": "REVIEW_SUBMITTED",
        "title": "Review submitted",
        "bodyJson": '{"namespace":"team-a","slug":"demo"}',
        "entityType": "SKILL",
        "entityId": 77,
        "status": "UNREAD",
        "createdAt": "2026-06-10T09:00:00Z",
        "readAt": None,
        "targetType": "REVIEW",
        "targetId": 77,
        "targetRoute": "/dashboard/reviews/77",
    }

    publish = build_notification_response(
        notification_row(category="PUBLISH", event_type="PUBLISHED", entity_type="SKILL", entity_id=31)
    )
    assert publish["targetType"] == "SKILL"
    assert publish["targetRoute"] == "/space/team-a/demo"


@pytest.mark.anyio
async def test_list_notifications_filters_category_and_uses_java_pagination_defaults() -> None:
    connection = FakeNotificationConnection(rows=[notification_row()], total=1)

    result = await list_notifications(FakeEngine(connection), user_id="user-1", category="REVIEW", page=0, size=20)

    assert result["total"] == 1
    assert result["page"] == 0
    assert result["size"] == 20
    assert result["items"][0]["id"] == 11
    assert connection.params[0]["recipient_id"] == "user-1"
    assert connection.params[0]["category"] == "REVIEW"
    assert connection.params[1]["limit"] == 20
    assert connection.params[1]["offset"] == 0


@pytest.mark.anyio
async def test_list_notifications_rejects_invalid_category() -> None:
    with pytest.raises(NotificationError, match="error.notification.category.invalid") as exc_info:
        await list_notifications(FakeEngine(FakeNotificationConnection()), user_id="user-1", category="BAD", page=0, size=20)

    assert exc_info.value.status_code == 400

    with pytest.raises(NotificationError, match="error.notification.category.invalid"):
        await list_notifications(FakeEngine(FakeNotificationConnection()), user_id="user-1", category="review", page=0, size=20)


@pytest.mark.anyio
async def test_unread_mark_all_and_delete_read_notifications() -> None:
    count_connection = FakeNotificationConnection(count=3)
    assert await unread_notification_count(FakeEngine(count_connection), "user-1") == {"count": 3}

    mark_all_connection = FakeNotificationConnection()
    mark_all_connection.updated = 2
    assert await mark_all_notifications_read(FakeEngine(mark_all_connection), "user-1") == {"updated": 2}

    delete_connection = FakeNotificationConnection()
    delete_connection.deleted = 1
    await delete_read_notification(FakeEngine(delete_connection), notification_id=11, user_id="user-1")

    missing_delete_connection = FakeNotificationConnection()
    with pytest.raises(NotificationError, match="error.notification.readNotFound") as exc_info:
        await delete_read_notification(FakeEngine(missing_delete_connection), notification_id=11, user_id="user-1")
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_mark_notification_read_enforces_missing_and_foreign_rules() -> None:
    missing_connection = FakeNotificationConnection()
    with pytest.raises(NotificationError, match="error.notification.notFound") as missing:
        await mark_notification_read(FakeEngine(missing_connection), notification_id=99, user_id="user-1")
    assert missing.value.status_code == 404

    foreign_connection = FakeNotificationConnection()
    foreign_connection.notification = notification_row(recipient_id="other-user")
    with pytest.raises(NotificationError, match="error.notification.noPermission") as forbidden:
        await mark_notification_read(FakeEngine(foreign_connection), notification_id=11, user_id="user-1")
    assert forbidden.value.status_code == 403

    success_connection = FakeNotificationConnection()
    success_connection.notification = notification_row(status="READ", read_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC))
    result = await mark_notification_read(FakeEngine(success_connection), notification_id=11, user_id="user-1")
    assert result["status"] == "READ"
    assert result["readAt"] == "2026-06-10T09:05:00Z"


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_notification_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.notification_list_reader = lambda user_id, category, page, size: {
        "items": [build_notification_response(notification_row())],
        "total": 1,
        "page": page,
        "size": size,
    }
    app.state.notification_unread_count_reader = lambda user_id: {"count": 1}
    app.state.notification_mark_read_writer = lambda notification_id, user_id: build_notification_response(
        notification_row(id=notification_id, status="READ", read_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC))
    )
    app.state.notification_mark_all_read_writer = lambda user_id: {"updated": 1}
    app.state.notification_delete_read_writer = lambda notification_id, user_id: None

    client = TestClient(app)

    assert client.get("/api/v1/notifications").status_code == 401

    list_response = client.get(
        "/api/web/notifications?page=2&size=5&category=REVIEW",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "notifications-list"},
    )
    unread_response = client.get("/api/v1/notifications/unread-count", headers={"X-Mock-User-Id": "user-1"})
    mark_response = client.put("/api/web/notifications/11/read", headers={"X-Mock-User-Id": "user-1"})
    mark_all_response = client.put("/api/v1/notifications/read-all", headers={"X-Mock-User-Id": "user-1"})
    delete_response = client.delete("/api/web/notifications/11", headers={"X-Mock-User-Id": "user-1"})

    assert list_response.status_code == 200
    assert list_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert list_response.json()["requestId"] == "notifications-list"
    assert list_response.json()["data"]["page"] == 2
    assert list_response.json()["data"]["size"] == 5
    assert unread_response.json()["data"] == {"count": 1}
    assert mark_response.status_code == 200
    assert mark_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert mark_response.json()["data"] is None
    assert mark_all_response.json()["data"] == {"updated": 1}
    assert delete_response.status_code == 200
    assert delete_response.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert delete_response.json()["data"] is None
