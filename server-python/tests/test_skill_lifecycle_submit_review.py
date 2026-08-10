from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillSubmitReviewInput,
    submit_skill_version_for_review,
)
from app.main import create_app


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeScalarResult(FakeResult):
    def __init__(self, scalar: int) -> None:
        super().__init__()
        self.scalar = scalar

    def scalar_one(self) -> int:
        return self.scalar

    def scalar_one_or_none(self) -> int:
        return self.scalar


class FakeTransaction:
    def __init__(self, connection: "FakeSubmitReviewConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSubmitReviewConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSubmitReviewConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeSubmitReviewConnection:
    def __init__(
        self,
        *,
        version_status: str = "UPLOADED",
        owner_id: str = "owner",
        namespace_role: str | None = None,
        duplicate_count: int = 0,
    ) -> None:
        self.version_status = version_status
        self.owner_id = owner_id
        self.namespace_role = namespace_role
        self.duplicate_count = duplicate_count
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM namespace n" in sql and "JOIN skill s" in sql:
            return FakeResult(
                {
                    "skill_id": 101,
                    "namespace_id": 20,
                    "namespace_slug": "team-a",
                    "namespace_status": "ACTIVE",
                    "skill_slug": "agent-helper",
                    "owner_id": self.owner_id,
                    "visibility": "PRIVATE",
                    "status": "ACTIVE",
                    "latest_version_id": None,
                }
            )
        if "FROM namespace_member nm" in sql and "notification_preference" in sql:
            return FakeResult(rows=[{"user_id": "team-admin"}])
        if "FROM namespace_member" in sql:
            return FakeResult({"role": self.namespace_role}) if self.namespace_role else FakeResult()
        if "FROM skill_version" in sql:
            return FakeResult({"version_id": 42, "version": "1.1.0", "status": self.version_status})
        if "SELECT COUNT(*)" in sql and "FROM review_task" in sql:
            return FakeScalarResult(self.duplicate_count)
        if "UPDATE skill_version" in sql:
            return FakeScalarResult(1)
        if "INSERT INTO review_task" in sql:
            return FakeResult({"id": 701})
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        if "INSERT INTO notification" in sql:
            row = {
                "id": 7200 + len(self.notifications),
                "recipient_id": values["recipient_id"],
                "category": values["category"],
                "event_type": values["event_type"],
                "title": values["title"],
                "body_json": values["body_json"],
                "entity_type": values["entity_type"],
                "entity_id": values["entity_id"],
                "created_at": values["created_at"],
            }
            self.notifications.append(row)
            return FakeResult(rows=[row])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeNotificationFanout:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.published.append((user_id, payload))


def submit_input(**overrides: Any) -> SkillSubmitReviewInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.1.0",
        "target_visibility": "NAMESPACE_ONLY",
        "user_id": "owner",
        "request_id": "req-submit-review",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 15, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillSubmitReviewInput(**data)


@pytest.mark.anyio
async def test_submit_skill_version_for_review_updates_version_creates_task_and_audits() -> None:
    connection = FakeSubmitReviewConnection()

    response = await submit_skill_version_for_review(FakeEngine(connection), submit_input())

    assert response == {"skillId": 101, "versionId": 42, "action": "SUBMIT_REVIEW", "status": "PENDING_REVIEW"}
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    review_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO review_task" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert version_update < review_insert < audit_insert
    assert connection.params[version_update]["status"] == "PENDING_REVIEW"
    assert connection.params[version_update]["requested_visibility"] == "NAMESPACE_ONLY"
    assert connection.params[review_insert]["namespace_id"] == 20
    assert connection.params[review_insert]["submitted_by"] == "owner"
    assert connection.params[audit_insert]["action"] == "SUBMIT_REVIEW"
    assert connection.params[audit_insert]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_insert]["target_id"] == 42
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {
        "version": "1.1.0",
        "targetVisibility": "NAMESPACE_ONLY",
    }


@pytest.mark.anyio
async def test_submit_skill_version_for_review_notifies_reviewers() -> None:
    connection = FakeSubmitReviewConnection()
    fanout = FakeNotificationFanout()

    await submit_skill_version_for_review(
        FakeEngine(connection),
        submit_input(),
        notification_fanout=fanout,
    )

    assert {row["recipient_id"] for row in connection.notifications} == {"team-admin"}
    assert {row["event_type"] for row in connection.notifications} == {"REVIEW_SUBMITTED"}
    body = json.loads(connection.notifications[0]["body_json"])
    assert body["reviewId"] == 701
    assert body["skillId"] == 101
    assert body["versionId"] == 42
    assert body["submitterId"] == "owner"
    assert body["namespace"] == "team-a"
    assert body["slug"] == "agent-helper"
    assert {recipient for recipient, _payload in fanout.published} == {"team-admin"}


@pytest.mark.anyio
async def test_submit_skill_version_for_review_persists_notification_without_fanout() -> None:
    connection = FakeSubmitReviewConnection()

    await submit_skill_version_for_review(
        FakeEngine(connection),
        submit_input(),
    )

    assert {row["recipient_id"] for row in connection.notifications} == {"team-admin"}
    assert {row["event_type"] for row in connection.notifications} == {"REVIEW_SUBMITTED"}


@pytest.mark.anyio
async def test_submit_skill_version_for_review_allows_namespace_manager_for_draft_version() -> None:
    connection = FakeSubmitReviewConnection(version_status="DRAFT", owner_id="owner", namespace_role="OWNER")

    response = await submit_skill_version_for_review(FakeEngine(connection), submit_input(user_id="manager", target_visibility="PUBLIC"))

    assert response["status"] == "PENDING_REVIEW"
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    assert connection.params[version_update]["requested_visibility"] == "PUBLIC"


@pytest.mark.anyio
async def test_submit_skill_version_for_review_rejects_invalid_visibility() -> None:
    connection = FakeSubmitReviewConnection()

    with pytest.raises(SkillLifecycleError, match="error.skill.review.visibility.invalid"):
        await submit_skill_version_for_review(FakeEngine(connection), submit_input(target_visibility="PRIVATE"))

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_submit_skill_version_for_review_rejects_non_uploaded_or_draft_version() -> None:
    connection = FakeSubmitReviewConnection(version_status="PUBLISHED")

    with pytest.raises(SkillLifecycleError, match="error.skill.version.submit.notUploaded"):
        await submit_skill_version_for_review(FakeEngine(connection), submit_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_submit_skill_version_for_review_rejects_non_manager_before_mutation() -> None:
    connection = FakeSubmitReviewConnection(owner_id="owner", namespace_role="MEMBER")

    with pytest.raises(SkillLifecycleError, match="error.skill.lifecycle.noPermission"):
        await submit_skill_version_for_review(FakeEngine(connection), submit_input(user_id="viewer"))

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_submit_skill_version_for_review_rejects_duplicate_pending_task() -> None:
    connection = FakeSubmitReviewConnection(duplicate_count=1)

    with pytest.raises(SkillLifecycleError, match="review.submit.duplicate"):
        await submit_skill_version_for_review(FakeEngine(connection), submit_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


def test_submit_review_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[SkillSubmitReviewInput] = []

    async def submitter(lifecycle_input: SkillSubmitReviewInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": 42, "action": "SUBMIT_REVIEW", "status": "PENDING_REVIEW"}

    app.state.skill_submit_review_writer = submitter
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/submit-review",
        json={"version": "1.1.0", "targetVisibility": "PUBLIC"},
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "submit-review-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["requestId"] == "submit-review-test"
    assert body["data"]["action"] == "SUBMIT_REVIEW"
    assert body["data"]["status"] == "PENDING_REVIEW"
    assert seen[0].namespace == "team-a"
    assert seen[0].version == "1.1.0"
    assert seen[0].target_visibility == "PUBLIC"


def test_submit_review_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post(
        "/api/v1/skills/team-a/agent-helper/submit-review",
        json={"version": "1.1.0", "targetVisibility": "PUBLIC"},
    ).status_code == 401
