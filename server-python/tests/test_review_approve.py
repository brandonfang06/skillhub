from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.approval import ReviewApproveInput, approve_review_task


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


class FakeReviewApproveConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []

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
            return FakeResult(scalar=1)
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "UPDATE skill" in sql:
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        if "FROM skill s" in sql and "JOIN skill_version sv ON sv.id = s.latest_version_id" in sql:
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
    assert review_update < version_update < skill_update < audit_insert
    assert audit_insert < search_upsert
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
