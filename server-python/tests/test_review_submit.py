from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.approval import ReviewSubmitInput, submit_review_task


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def scalar_one(self) -> Any:
        return self.scalar


class FakeReviewSubmitConnection:
    def __init__(self, *, duplicate_count: int = 0, version_status: str = "UPLOADED") -> None:
        self.duplicate_count = duplicate_count
        self.version_status = version_status
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM skill_version sv" in sql:
            return FakeResult(
                row={
                    "skill_version_id": 52,
                    "version_status": self.version_status,
                    "version_name": "1.0.0",
                    "namespace_id": 10,
                    "namespace_slug": "team-a",
                    "namespace_type": "TEAM",
                    "namespace_status": "ACTIVE",
                    "skill_id": 17,
                    "skill_slug": "agent-helper",
                    "owner_id": "local-user",
                    "submitted_by_name": "Local User",
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[])
        if "FROM namespace_member nm" in sql and "notification_preference" in sql:
            return FakeResult(rows=[{"user_id": "team-admin"}])
        if "FROM namespace_member" in sql:
            return FakeResult(row=None)
        if "FROM review_task" in sql and "COUNT" in sql:
            return FakeResult(scalar=self.duplicate_count)
        if "UPDATE skill_version" in sql:
            return FakeResult(scalar=1)
        if "INSERT INTO review_task" in sql:
            return FakeResult(row={"id": 901, "submitted_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC)})
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        if "INSERT INTO notification" in sql:
            values = params or {}
            row = {
                "id": 7400 + len(self.notifications),
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
    def __init__(self, connection: FakeReviewSubmitConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewSubmitConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewSubmitConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)


def submit_input(**overrides: Any) -> ReviewSubmitInput:
    data = {
        "skill_version_id": 52,
        "user_id": "local-user",
        "request_id": "req-submit",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return ReviewSubmitInput(**data)


@pytest.mark.anyio
async def test_submit_review_task_moves_version_creates_task_and_audits() -> None:
    connection = FakeReviewSubmitConnection()

    response = await submit_review_task(FakeEngine(connection), submit_input())

    assert response["id"] == 901
    assert response["skillVersionId"] == 52
    assert response["status"] == "PENDING"
    assert response["submittedBy"] == "local-user"
    assert response["reviewedBy"] is None
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    task_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO review_task" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert version_update < task_insert < audit_insert
    assert connection.params[version_update]["status"] == "PENDING_REVIEW"
    assert connection.params[task_insert]["skill_version_id"] == 52
    assert connection.params[task_insert]["namespace_id"] == 10
    assert connection.params[task_insert]["submitted_by"] == "local-user"
    assert connection.params[audit_insert]["action"] == "REVIEW_SUBMIT"
    assert connection.params[audit_insert]["target_type"] == "REVIEW_TASK"
    assert connection.params[audit_insert]["target_id"] == 901
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"skillVersionId": 52}


@pytest.mark.anyio
async def test_submit_review_task_persists_review_notification_without_fanout() -> None:
    connection = FakeReviewSubmitConnection()

    await submit_review_task(FakeEngine(connection), submit_input())

    assert {row["recipient_id"] for row in connection.notifications} == {"team-admin"}
    assert {row["event_type"] for row in connection.notifications} == {"REVIEW_SUBMITTED"}


@pytest.mark.anyio
async def test_submit_review_task_rejects_duplicate_pending_task() -> None:
    connection = FakeReviewSubmitConnection(duplicate_count=1)

    with pytest.raises(ValueError, match="review.submit.duplicate"):
        await submit_review_task(FakeEngine(connection), submit_input())

    assert not any("UPDATE skill_version" in sql for sql in connection.statements)
    assert not any("INSERT INTO review_task" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_submit_review_task_rejects_non_draft_or_uploaded_version() -> None:
    connection = FakeReviewSubmitConnection(version_status="PENDING_REVIEW")

    with pytest.raises(ValueError, match="review.submit.not_draft"):
        await submit_review_task(FakeEngine(connection), submit_input())


def test_review_submit_route_returns_java_created_envelope() -> None:
    app = create_app()
    seen: list[ReviewSubmitInput] = []

    async def submitter(review_input: ReviewSubmitInput) -> dict[str, object]:
        seen.append(review_input)
        return {
            "id": 901,
            "skillVersionId": review_input.skill_version_id,
            "namespace": "team-a",
            "skillSlug": "agent-helper",
            "version": "1.0.0",
            "status": "PENDING",
            "submittedBy": review_input.user_id,
            "submittedByName": "Local User",
            "reviewedBy": None,
            "reviewedByName": None,
            "reviewComment": None,
            "submittedAt": "2026-06-09T12:00:00Z",
            "reviewedAt": None,
        }

    app.state.review_submit_writer = submitter
    client = TestClient(app)

    response = client.post(
        "/api/web/reviews",
        json={"skillVersionId": 52},
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "review-submit-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u521b\u5efa\u6210\u529f"
    assert body["requestId"] == "review-submit-test"
    assert body["data"]["status"] == "PENDING"
    assert seen[0].skill_version_id == 52
    assert seen[0].user_id == "local-user"


def test_review_submit_route_requires_mock_user() -> None:
    app = create_app()
    app.state.review_submit_writer = lambda review_input: {}
    client = TestClient(app)

    response = client.post("/api/v1/reviews", json={"skillVersionId": 52})

    assert response.status_code == 401
