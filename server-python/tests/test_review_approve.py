from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.approval import ReviewApprovalError, ReviewApproveInput, approve_review_task


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def first(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeReviewApproveConnection:
    def __init__(
        self,
        *,
        current_visibility: str = "NAMESPACE_ONLY",
        visibility_updated_after_submission: bool = False,
        review_update_result: int | None = 1,
    ) -> None:
        self.current_visibility = current_visibility
        self.visibility_updated_after_submission = visibility_updated_after_submission
        self.review_update_result = review_update_result
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM review_task rt" in sql:
            return FakeResult(
                row={
                    "id": 701,
                    "skill_version_id": 42,
                    "namespace_id": 10,
                    "status": "PENDING",
                    "version": 1,
                    "submitted_by": "local-user",
                    "submitted_by_name": "Local User",
                    "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    "namespace_slug": "team-a",
                    "namespace_type": "TEAM",
                    "namespace_status": "ACTIVE",
                    "skill_id": 7,
                    "skill_slug": "agent-helper",
                    "owner_id": "local-user",
                    "version_name": "1.0.0",
                    "version_status": "PENDING_REVIEW",
                    "requested_visibility": "NAMESPACE_ONLY",
                    "parsed_metadata_json": json.dumps({"name": "Agent Helper", "description": "Helps agents"}),
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[])
        if "FROM namespace_member" in sql:
            return FakeResult(row={"role": "ADMIN"})
        if "SELECT COUNT(*)" in sql and "FROM skill other" in sql:
            return FakeResult(scalar=0)
        if "UPDATE review_task" in sql:
            return FakeResult(scalar=self.review_update_result)
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "SELECT visibility" in sql and "FROM skill" in sql:
            return FakeResult(row={"visibility": self.current_visibility})
        if "SELECT EXISTS" in sql and "UPDATE_SKILL_VISIBILITY" in sql:
            return FakeResult(scalar=self.visibility_updated_after_submission)
        if "UPDATE skill" in sql:
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        if "FROM skill s" in sql and "JOIN LATERAL" in sql:
            return FakeResult(
                row={
                    "skill_id": 7,
                    "namespace_id": 10,
                    "namespace_slug": "team-a",
                    "owner_id": "local-user",
                    "slug": "agent-helper",
                    "display_name": "Agent Helper",
                    "summary": "Helps agents",
                    "visibility": "NAMESPACE_ONLY",
                    "status": "ACTIVE",
                    "parsed_metadata_json": json.dumps({"name": "Agent Helper", "description": "Helps agents"}),
                }
            )
        if "FROM skill_label sl" in sql:
            return FakeResult(rows=[])
        if "INSERT INTO skill_search_document" in sql:
            return FakeResult()
        if "notification_preference" in sql:
            return FakeResult(row={"enabled": True})
        if "INSERT INTO notification" in sql:
            values = params or {}
            row = {
                "id": 7100 + len(self.notifications),
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


class FakeBegin:
    def __init__(self, connection: FakeReviewApproveConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewApproveConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewApproveConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)


class FakeNotificationFanout:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.published.append((user_id, payload))


def approve_input(**overrides: Any) -> ReviewApproveInput:
    data = {
        "review_task_id": 701,
        "reviewer_id": "team-admin",
        "comment": "ship it",
        "request_id": "req-approve",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return ReviewApproveInput(**data)


@pytest.mark.anyio
async def test_approve_review_task_publishes_version_updates_skill_and_audit() -> None:
    connection = FakeReviewApproveConnection()

    response = await approve_review_task(FakeEngine(connection), approve_input())

    assert response["id"] == 701
    assert response["status"] == "APPROVED"
    assert response["reviewedBy"] == "team-admin"
    assert response["reviewComment"] == "ship it"
    review_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE review_task" in sql)
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    search_upsert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO skill_search_document" in sql)
    skill_lock = next(sql for sql in connection.statements if "SELECT visibility" in sql and "FROM skill" in sql)
    search_source = next(sql for sql in connection.statements if "FROM skill s" in sql and "JOIN LATERAL" in sql)
    assert review_update < version_update < skill_update < audit_insert
    assert audit_insert < search_upsert
    assert "sv.status = 'PUBLISHED'" in search_source
    assert "FOR UPDATE" in skill_lock
    assert connection.params[review_update]["status"] == "APPROVED"
    assert connection.params[version_update]["status"] == "PUBLISHED"
    assert connection.params[skill_update]["latest_version_id"] == 42
    assert connection.params[skill_update]["visibility"] == "NAMESPACE_ONLY"
    assert connection.params[skill_update]["display_name"] == "Agent Helper"
    assert connection.params[skill_update]["summary"] == "Helps agents"
    assert connection.params[audit_insert]["action"] == "REVIEW_APPROVE"
    assert connection.params[audit_insert]["target_type"] == "REVIEW_TASK"
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"comment": "ship it"}
    assert connection.params[search_upsert]["skill_id"] == 7


@pytest.mark.anyio
async def test_approve_review_task_preserves_visibility_changed_after_submission() -> None:
    connection = FakeReviewApproveConnection(
        current_visibility="PRIVATE",
        visibility_updated_after_submission=True,
    )

    await approve_review_task(FakeEngine(connection), approve_input())

    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    visibility_audit_check = next(
        index
        for index, sql in enumerate(connection.statements)
        if "SELECT EXISTS" in sql and "UPDATE_SKILL_VISIBILITY" in sql
    )
    assert connection.params[skill_update]["visibility"] == "PRIVATE"
    assert connection.params[visibility_audit_check]["submitted_at"] == datetime(
        2026,
        6,
        9,
        10,
        0,
        tzinfo=UTC,
    )


@pytest.mark.anyio
async def test_approve_review_task_maps_lost_optimistic_update_to_conflict() -> None:
    connection = FakeReviewApproveConnection(review_update_result=None)

    with pytest.raises(ReviewApprovalError) as error:
        await approve_review_task(FakeEngine(connection), approve_input())

    assert str(error.value) == "review.concurrent_update"
    assert error.value.status_code == 409
    assert not any("UPDATE skill_version" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_approve_review_task_notifies_submitter() -> None:
    connection = FakeReviewApproveConnection()
    fanout = FakeNotificationFanout()

    await approve_review_task(
        FakeEngine(connection),
        approve_input(),
        notification_fanout=fanout,
    )

    assert len(connection.notifications) == 1
    notification = connection.notifications[0]
    assert notification["recipient_id"] == "local-user"
    assert notification["category"] == "REVIEW"
    assert notification["event_type"] == "REVIEW_APPROVED"
    assert notification["entity_type"] == "SKILL"
    assert notification["entity_id"] == 7
    body = json.loads(notification["body_json"])
    assert body["reviewId"] == 701
    assert body["skillId"] == 7
    assert body["versionId"] == 42
    assert body["reviewerId"] == "team-admin"
    assert body["namespace"] == "team-a"
    assert body["slug"] == "agent-helper"
    assert body["skillName"] == "Agent Helper"
    assert fanout.published == [
        (
            "local-user",
            {
                "id": 7100,
                "category": "REVIEW",
                "eventType": "REVIEW_APPROVED",
                "title": "Review approved: Agent Helper",
                "bodyJson": notification["body_json"],
                "entityType": "SKILL",
                "entityId": 7,
                "createdAt": "2026-06-09T11:00:00Z",
            },
        )
    ]


@pytest.mark.anyio
async def test_approve_review_task_persists_notification_without_fanout() -> None:
    connection = FakeReviewApproveConnection()

    await approve_review_task(FakeEngine(connection), approve_input())

    assert len(connection.notifications) == 1
    assert connection.notifications[0]["recipient_id"] == "local-user"
    assert connection.notifications[0]["event_type"] == "REVIEW_APPROVED"


def test_review_approve_route_returns_java_envelope() -> None:
    app = create_app()
    seen: list[ReviewApproveInput] = []

    async def approver(review_input: ReviewApproveInput) -> dict[str, object]:
        seen.append(review_input)
        return {
            "id": 701,
            "skillVersionId": 42,
            "namespace": "team-a",
            "skillSlug": "agent-helper",
            "version": "1.0.0",
            "status": "APPROVED",
            "submittedBy": "local-user",
            "submittedByName": "Local User",
            "reviewedBy": "team-admin",
            "reviewedByName": None,
            "reviewComment": "ship it",
            "submittedAt": "2026-06-09T10:00:00Z",
            "reviewedAt": "2026-06-09T11:00:00Z",
        }

    app.state.review_approve_writer = approver
    client = TestClient(app)

    response = client.post(
        "/api/v1/reviews/701/approve",
        json={"comment": "ship it"},
        headers={"X-Mock-User-Id": "team-admin", "X-Request-Id": "review-approve-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "更新成功"
    assert body["requestId"] == "review-approve-test"
    assert body["data"]["status"] == "APPROVED"
    assert seen[0].review_task_id == 701
    assert seen[0].reviewer_id == "team-admin"
    assert seen[0].comment == "ship it"


def test_review_approve_route_requires_mock_user() -> None:
    app = create_app()
    app.state.review_approve_writer = lambda review_input: {}
    client = TestClient(app)

    response = client.post("/api/v1/reviews/701/approve")

    assert response.status_code == 401
