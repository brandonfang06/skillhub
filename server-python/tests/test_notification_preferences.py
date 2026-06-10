from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications.preferences import (
    NotificationPreferenceError,
    get_notification_preferences,
    update_notification_preferences,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self.rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnect:
    def __init__(self, connection: "FakePreferenceConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakePreferenceConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakePreferenceConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)

    def begin(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakePreferenceConnection:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)
        if "SELECT category, channel, enabled" in sql:
            return FakeResult(rows=self.rows)
        if "INSERT INTO notification_preference" in sql:
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


@pytest.mark.anyio
async def test_get_notification_preferences_returns_java_defaults_and_saved_overlay() -> None:
    connection = FakePreferenceConnection(rows=[{"category": "REVIEW", "channel": "IN_APP", "enabled": False}])

    result = await get_notification_preferences(FakeEngine(connection), "user-1")

    assert result == [
        {"category": "PUBLISH", "channel": "IN_APP", "enabled": True},
        {"category": "REVIEW", "channel": "IN_APP", "enabled": False},
        {"category": "PROMOTION", "channel": "IN_APP", "enabled": True},
        {"category": "REPORT", "channel": "IN_APP", "enabled": True},
    ]
    assert connection.params[0] == {"user_id": "user-1"}


@pytest.mark.anyio
async def test_update_notification_preferences_validates_java_error_cases() -> None:
    engine = FakeEngine(FakePreferenceConnection())

    with pytest.raises(NotificationPreferenceError, match="error.notification.preference.request.invalid") as missing:
        await update_notification_preferences(engine, "user-1", None)
    assert missing.value.status_code == 400

    with pytest.raises(NotificationPreferenceError, match="error.notification.preference.category.invalid"):
        await update_notification_preferences(engine, "user-1", [{"category": "review", "channel": "IN_APP", "enabled": True}])

    with pytest.raises(NotificationPreferenceError, match="error.notification.preference.channel.invalid"):
        await update_notification_preferences(engine, "user-1", [{"category": "REVIEW", "channel": "email", "enabled": True}])

    with pytest.raises(NotificationPreferenceError, match="error.notification.preference.channel.invalid"):
        await update_notification_preferences(engine, "user-1", [{"category": "REVIEW", "channel": "EMAIL", "enabled": True}])

    with pytest.raises(NotificationPreferenceError, match="error.notification.preference.duplicate"):
        await update_notification_preferences(
            engine,
            "user-1",
            [
                {"category": "REVIEW", "channel": "IN_APP", "enabled": True},
                {"category": "REVIEW", "channel": "IN_APP", "enabled": False},
            ],
        )


@pytest.mark.anyio
async def test_update_notification_preferences_upserts_and_returns_full_view() -> None:
    connection = FakePreferenceConnection(rows=[{"category": "PUBLISH", "channel": "IN_APP", "enabled": False}])

    result = await update_notification_preferences(
        FakeEngine(connection),
        "user-1",
        [{"category": "PUBLISH", "channel": "IN_APP", "enabled": False}],
    )

    assert result[0] == {"category": "PUBLISH", "channel": "IN_APP", "enabled": False}
    assert "ON CONFLICT" in connection.statements[0]
    assert connection.params[0] == {
        "user_id": "user-1",
        "category": "PUBLISH",
        "channel": "IN_APP",
        "enabled": False,
    }


def test_notification_preference_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.notification_preference_reader = lambda user_id: [
        {"category": "PUBLISH", "channel": "IN_APP", "enabled": True},
        {"category": "REVIEW", "channel": "IN_APP", "enabled": False},
    ]
    app.state.notification_preference_writer = lambda user_id, preferences: [
        {"category": "PUBLISH", "channel": "IN_APP", "enabled": False},
        {"category": "REVIEW", "channel": "IN_APP", "enabled": False},
    ]

    client = TestClient(app)

    assert client.get("/api/v1/notification-preferences").status_code == 401

    get_response = client.get(
        "/api/web/notification-preferences",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "preference-get"},
    )
    put_response = client.put(
        "/api/v1/notification-preferences",
        json={"preferences": [{"category": "PUBLISH", "channel": "IN_APP", "enabled": False}]},
        headers={"X-Mock-User-Id": "user-1"},
    )
    bad_response = client.put(
        "/api/v1/notification-preferences",
        json={},
        headers={"X-Mock-User-Id": "user-1"},
    )

    assert get_response.status_code == 200
    assert get_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert get_response.json()["requestId"] == "preference-get"
    assert get_response.json()["data"][1]["enabled"] is False
    assert put_response.status_code == 200
    assert put_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert put_response.json()["data"][0] == {"category": "PUBLISH", "channel": "IN_APP", "enabled": False}
    assert bad_response.status_code == 400
