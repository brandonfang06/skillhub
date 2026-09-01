from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.subscription import (
    SkillSubscriptionError,
    SkillSubscriptionInput,
    check_skill_subscription,
    subscribe_skill,
    unsubscribe_skill,
)


class FakeScalarResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def mappings(self) -> "FakeScalarResult":
        return self

    def one_or_none(self) -> Any:
        return self.value


class FakeTransaction:
    def __init__(self, connection: "FakeSubscriptionConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSubscriptionConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnect:
    def __init__(self, connection: "FakeSubscriptionConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSubscriptionConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSubscriptionConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeSubscriptionConnection:
    def __init__(
        self,
        *,
        skill_exists: bool = True,
        already_subscribed: bool = False,
        visibility: str = "PUBLIC",
        hidden: bool = False,
        namespace_status: str = "ACTIVE",
        account_status: str | None = "ACTIVE",
        role: str | None = None,
        published_version_id: int | None = 42,
    ) -> None:
        self.skill_exists = skill_exists
        self.subscribed = already_subscribed
        self.visibility = visibility
        self.hidden = hidden
        self.namespace_status = namespace_status
        self.account_status = account_status
        self.role = role
        self.published_version_id = published_version_id
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeScalarResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM skill s" in sql and "JOIN namespace n" in sql:
            if not self.skill_exists:
                return FakeScalarResult(None)
            return FakeScalarResult(
                {
                    "skill_id": 10,
                    "namespace_id": 5,
                    "owner_id": "owner",
                    "visibility": self.visibility,
                    "hidden": self.hidden,
                    "latest_version_id": 43,
                    "published_version_id": self.published_version_id,
                    "namespace_status": self.namespace_status,
                    "account_status": self.account_status,
                    "namespace_role": self.role,
                }
            )
        if "SELECT 1" in sql and "FROM skill_subscription" in sql:
            return FakeScalarResult(1 if self.subscribed else None)
        if "SELECT 1" in sql and "FROM skill" in sql:
            return FakeScalarResult(1 if self.skill_exists else None)
        if "INSERT INTO skill_subscription" in sql:
            self.subscribed = True
            return FakeScalarResult()
        if "DELETE FROM skill_subscription" in sql:
            self.subscribed = False
            return FakeScalarResult()
        if "UPDATE skill" in sql and "subscription_count" in sql:
            return FakeScalarResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def normalized(sql: str) -> str:
    return " ".join(sql.split())


def subscription_input(**overrides: Any) -> SkillSubscriptionInput:
    data: dict[str, Any] = {
        "skill_id": 10,
        "user_id": "user-1",
        "now": datetime(2026, 6, 10, 10, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillSubscriptionInput(**data)


@pytest.mark.anyio
async def test_subscribe_skill_creates_relationship_and_increments_count_idempotently() -> None:
    connection = FakeSubscriptionConnection()

    await subscribe_skill(FakeEngine(connection), subscription_input())
    await subscribe_skill(FakeEngine(connection), subscription_input())

    insert_count = sum(1 for sql in connection.statements if "INSERT INTO skill_subscription" in normalized(sql))
    increment_count = sum(
        1
        for sql in connection.statements
        if "UPDATE skill" in sql and "subscription_count = subscription_count + 1" in normalized(sql)
    )
    assert insert_count == 1
    assert increment_count == 1
    insert_params = next(
        params
        for sql, params in zip(connection.statements, connection.params, strict=True)
        if "INSERT INTO skill_subscription" in normalized(sql)
    )
    assert insert_params["skill_id"] == 10
    assert insert_params["user_id"] == "user-1"
    assert insert_params["created_at"] == datetime(2026, 6, 10, 10, 30, tzinfo=UTC)


@pytest.mark.anyio
async def test_public_skill_without_published_version_cannot_be_subscribed() -> None:
    connection = FakeSubscriptionConnection(published_version_id=None)

    with pytest.raises(SkillSubscriptionError) as exc_info:
        await subscribe_skill(FakeEngine(connection), subscription_input())

    assert exc_info.value.status_code == 403
    assert connection.subscribed is False


@pytest.mark.anyio
async def test_unsubscribe_skill_deletes_relationship_and_decrements_count_idempotently() -> None:
    connection = FakeSubscriptionConnection(already_subscribed=True)

    await unsubscribe_skill(FakeEngine(connection), subscription_input())
    await unsubscribe_skill(FakeEngine(connection), subscription_input())

    delete_count = sum(1 for sql in connection.statements if "DELETE FROM skill_subscription" in normalized(sql))
    decrement_count = sum(1 for sql in connection.statements if "subscription_count > 0" in normalized(sql))
    assert delete_count == 1
    assert decrement_count == 1


@pytest.mark.anyio
async def test_check_skill_subscription_returns_false_for_anonymous_and_validates_authenticated_skill() -> None:
    anonymous_connection = FakeSubscriptionConnection(skill_exists=False, already_subscribed=True)
    assert await check_skill_subscription(FakeEngine(anonymous_connection), 10, None) is False
    assert not anonymous_connection.statements

    authenticated_connection = FakeSubscriptionConnection(already_subscribed=True)
    assert await check_skill_subscription(FakeEngine(authenticated_connection), 10, "user-1") is True


@pytest.mark.anyio
async def test_skill_subscription_raises_not_found_before_mutation() -> None:
    connection = FakeSubscriptionConnection(skill_exists=False)

    with pytest.raises(SkillSubscriptionError, match="skill.not_found") as exc_info:
        await subscribe_skill(FakeEngine(connection), subscription_input())

    assert exc_info.value.status_code == 404
    assert not any("INSERT INTO skill_subscription" in sql for sql in connection.statements)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("visibility", "hidden", "namespace_status", "account_status", "role"),
    [
        ("NAMESPACE_ONLY", False, "ACTIVE", "ACTIVE", None),
        ("PRIVATE", False, "ACTIVE", "ACTIVE", "MEMBER"),
        ("PUBLIC", True, "ACTIVE", "ACTIVE", "MEMBER"),
        ("PUBLIC", False, "ARCHIVED", "ACTIVE", None),
        ("PUBLIC", False, "ACTIVE", "DISABLED", None),
    ],
)
async def test_subscribe_rechecks_current_metadata_access_before_mutation(
    visibility: str,
    hidden: bool,
    namespace_status: str,
    account_status: str,
    role: str | None,
) -> None:
    connection = FakeSubscriptionConnection(
        visibility=visibility,
        hidden=hidden,
        namespace_status=namespace_status,
        account_status=account_status,
        role=role,
    )

    with pytest.raises(
        SkillSubscriptionError,
        match="error.skill.subscription.noPermission",
    ) as exc_info:
        await subscribe_skill(FakeEngine(connection), subscription_input())

    assert exc_info.value.status_code == 403
    assert not any("INSERT INTO skill_subscription" in sql for sql in connection.statements)
    assert not any("subscription_count = subscription_count + 1" in sql for sql in connection.statements)


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_skill_subscription_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    seen: list[SkillSubscriptionInput] = []
    subscribed = {"value": False}
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def subscribe_writer(subscription_input_value: SkillSubscriptionInput) -> None:
        seen.append(subscription_input_value)
        subscribed["value"] = True

    async def unsubscribe_writer(subscription_input_value: SkillSubscriptionInput) -> None:
        seen.append(subscription_input_value)
        subscribed["value"] = False

    async def reader(skill_id: int, user_id: str | None) -> bool:
        return bool(subscribed["value"] and user_id == "user-1" and skill_id == 10)

    app.state.skill_subscription_writer = subscribe_writer
    app.state.skill_unsubscribe_writer = unsubscribe_writer
    app.state.skill_subscription_reader = reader
    client = TestClient(app)

    anonymous_check = client.get("/api/v1/skills/10/subscription")
    missing_user = client.put("/api/v1/skills/10/subscription", headers={"X-Request-Id": "subscription-missing-user"})

    subscribe_response = client.put(
        "/api/v1/skills/10/subscription",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "subscription-test"},
    )
    check_response = client.get("/api/web/skills/10/subscription", headers={"X-Mock-User-Id": "user-1"})
    unsubscribe_response = client.delete("/api/web/skills/10/subscription", headers={"X-Mock-User-Id": "user-1"})

    assert anonymous_check.status_code == 200
    assert anonymous_check.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert anonymous_check.json()["data"] is False
    assert missing_user.status_code == 401
    assert subscribe_response.status_code == 200
    assert subscribe_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert subscribe_response.json()["data"] is None
    assert subscribe_response.json()["requestId"] == "subscription-test"
    assert check_response.status_code == 200
    assert check_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert check_response.json()["data"] is True
    assert unsubscribe_response.status_code == 200
    assert unsubscribe_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert unsubscribe_response.json()["data"] is None
    assert [entry.skill_id for entry in seen] == [10, 10]
    assert [entry.user_id for entry in seen] == ["user-1", "user-1"]
