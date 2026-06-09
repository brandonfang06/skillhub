from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.approval import (
    ReviewRejectInput,
    ReviewWithdrawInput,
    reject_review_task,
    withdraw_review_task,
)


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


class FakeReviewLifecycleConnection:
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
                    "id": 801,
                    "skill_version_id": 52,
                    "namespace_id": 10,
                    "status": "PENDING",
                    "version": 1,
                    "submitted_by": "local-user",
                    "submitted_by_name": "Local User",
                    "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    "namespace_slug": "team-a",
                    "namespace_type": "TEAM",
                    "namespace_status": "ACTIVE",
                    "skill_id": 17,
                    "skill_slug": "agent-helper",
                    "owner_id": "local-user",
                    "version_name": "1.0.0",
                    "version_status": "PENDING_REVIEW",
                    "requested_visibility": "NAMESPACE_ONLY",
                    "parsed_metadata_json": json.dumps({"name": "Agent Helper"}),
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[])
        if "FROM namespace_member" in sql:
            return FakeResult(row={"role": "ADMIN"})
        if "UPDATE review_task" in sql:
            return FakeResult(scalar=1)
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "UPDATE skill" in sql:
            return FakeResult()
        if "DELETE FROM review_task" in sql:
            return FakeResult(scalar=1)
        if "INSERT INTO audit_log" in sql:
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {sql}")


class FakeBegin:
    def __init__(self, connection: FakeReviewLifecycleConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewLifecycleConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewLifecycleConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)


@pytest.mark.anyio
async def test_reject_review_task_rejects_task_version_and_audits() -> None:
    connection = FakeReviewLifecycleConnection()

    response = await reject_review_task(
        FakeEngine(connection),
        ReviewRejectInput(
            review_task_id=801,
            reviewer_id="team-admin",
            comment="needs changes",
            request_id="req-reject",
            client_ip="127.0.0.1",
            user_agent="pytest",
            now=datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
        ),
    )

    assert response["status"] == "REJECTED"
    assert response["reviewedBy"] == "team-admin"
    review_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE review_task" in sql)
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert review_update < version_update < audit_insert
    assert connection.params[review_update]["status"] == "REJECTED"
    assert connection.params[version_update]["status"] == "REJECTED"
    assert connection.params[audit_insert]["action"] == "REVIEW_REJECT"
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"comment": "needs changes"}


@pytest.mark.anyio
async def test_withdraw_review_task_deletes_pending_task_reopens_version_and_audits() -> None:
    connection = FakeReviewLifecycleConnection()

    result = await withdraw_review_task(
        FakeEngine(connection),
        ReviewWithdrawInput(
            review_task_id=801,
            user_id="local-user",
            request_id="req-withdraw",
            client_ip="127.0.0.1",
            user_agent="pytest",
            now=datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
        ),
    )

    assert result is None
    delete_task = next(index for index, sql in enumerate(connection.statements) if "DELETE FROM review_task" in sql)
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert delete_task < version_update < skill_update < audit_insert
    assert connection.params[version_update]["status"] == "UPLOADED"
    assert connection.params[skill_update]["updated_by"] == "local-user"
    assert connection.params[audit_insert]["action"] == "REVIEW_WITHDRAW"
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"skillVersionId": 52}


def test_reject_route_returns_java_envelope() -> None:
    app = create_app()

    async def rejecter(review_input: ReviewRejectInput) -> dict[str, object]:
        return {
            "id": review_input.review_task_id,
            "skillVersionId": 52,
            "namespace": "team-a",
            "skillSlug": "agent-helper",
            "version": "1.0.0",
            "status": "REJECTED",
            "submittedBy": "local-user",
            "submittedByName": "Local User",
            "reviewedBy": review_input.reviewer_id,
            "reviewedByName": None,
            "reviewComment": review_input.comment,
            "submittedAt": "2026-06-09T10:00:00Z",
            "reviewedAt": "2026-06-09T11:00:00Z",
        }

    app.state.review_reject_writer = rejecter
    client = TestClient(app)

    response = client.post(
        "/api/v1/reviews/801/reject",
        json={"comment": "needs changes"},
        headers={"X-Mock-User-Id": "team-admin", "X-Request-Id": "review-reject-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "更新成功"
    assert body["requestId"] == "review-reject-test"
    assert body["data"]["status"] == "REJECTED"
    assert body["data"]["reviewComment"] == "needs changes"


def test_withdraw_route_returns_null_data_java_envelope() -> None:
    app = create_app()

    async def withdrawer(review_input: ReviewWithdrawInput) -> None:
        assert review_input.review_task_id == 801
        assert review_input.user_id == "local-user"
        return None

    app.state.review_withdraw_writer = withdrawer
    client = TestClient(app)

    response = client.post(
        "/api/web/reviews/801/withdraw",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "review-withdraw-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "更新成功"
    assert body["requestId"] == "review-withdraw-test"
    assert body["data"] is None
