from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillVersionWithdrawReviewInput,
    withdraw_skill_version_review,
)
from app.main import create_app


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class FakeTransaction:
    def __init__(self, connection: "FakeWithdrawReviewConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeWithdrawReviewConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeWithdrawReviewConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeWithdrawReviewConnection:
    def __init__(
        self,
        *,
        version_status: str = "PENDING_REVIEW",
        review_task: dict[str, Any] | None = None,
        owner_id: str = "owner",
        namespace_status: str = "ACTIVE",
    ) -> None:
        self.version_status = version_status
        self.review_task = review_task
        self.owner_id = owner_id
        self.namespace_status = namespace_status
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

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
                    "namespace_status": self.namespace_status,
                    "skill_slug": "agent-helper",
                    "owner_id": self.owner_id,
                    "status": "ACTIVE",
                    "latest_version_id": 42,
                }
            )
        if "FROM skill_version" in sql:
            return FakeResult({"version_id": 42, "version": "1.1.0", "status": self.version_status})
        if "FROM review_task" in sql:
            if self.review_task is None:
                return FakeResult(
                    {
                        "review_task_id": 701,
                        "submitted_by": "publisher",
                        "status": "PENDING",
                    }
                )
            return FakeResult(self.review_task)
        if "DELETE FROM review_task" in sql:
            return FakeResult()
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "UPDATE skill" in sql:
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def withdraw_input(**overrides: Any) -> SkillVersionWithdrawReviewInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.1.0",
        "user_id": "publisher",
        "request_id": "req-withdraw-version",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 13, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillVersionWithdrawReviewInput(**data)


@pytest.mark.anyio
async def test_withdraw_skill_version_review_deletes_task_reopens_version_updates_skill_and_audits() -> None:
    connection = FakeWithdrawReviewConnection()

    response = await withdraw_skill_version_review(FakeEngine(connection), withdraw_input())

    assert response == {"skillId": 101, "versionId": 42, "action": "WITHDRAW_REVIEW", "status": "UPLOADED"}
    delete_task = next(index for index, sql in enumerate(connection.statements) if "DELETE FROM review_task" in sql)
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert delete_task < version_update < skill_update < audit_insert
    assert "updated_at" not in connection.statements[version_update]
    assert connection.params[version_update]["status"] == "UPLOADED"
    assert connection.params[skill_update]["updated_by"] == "publisher"
    assert connection.params[audit_insert]["action"] == "REVIEW_WITHDRAW"
    assert connection.params[audit_insert]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_insert]["target_id"] == 42
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"version": "1.1.0"}


@pytest.mark.anyio
async def test_withdraw_skill_version_review_rejects_non_submitter_before_mutation() -> None:
    connection = FakeWithdrawReviewConnection(review_task={"review_task_id": 701, "submitted_by": "publisher", "status": "PENDING"})

    with pytest.raises(SkillLifecycleError, match="review.withdraw.not_submitter"):
        await withdraw_skill_version_review(FakeEngine(connection), withdraw_input(user_id="other-user"))

    assert not any("DELETE FROM review_task" in statement for statement in connection.statements)
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_withdraw_skill_version_review_requires_pending_review_version() -> None:
    connection = FakeWithdrawReviewConnection(version_status="UPLOADED")

    with pytest.raises(SkillLifecycleError, match="review.withdraw.not_pending"):
        await withdraw_skill_version_review(FakeEngine(connection), withdraw_input())

    assert not any("DELETE FROM review_task" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_withdraw_skill_version_review_requires_pending_task() -> None:
    connection = FakeWithdrawReviewConnection(review_task={})

    with pytest.raises(SkillLifecycleError, match="review_task.not_found_for_version"):
        await withdraw_skill_version_review(FakeEngine(connection), withdraw_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_withdraw_skill_version_review_rejects_frozen_namespace_like_java() -> None:
    connection = FakeWithdrawReviewConnection(namespace_status="FROZEN")

    with pytest.raises(SkillLifecycleError, match="error.namespace.frozen") as exc_info:
        await withdraw_skill_version_review(FakeEngine(connection), withdraw_input())

    assert exc_info.value.status_code == 400
    assert not any("DELETE FROM review_task" in statement for statement in connection.statements)
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_withdraw_skill_version_review_rejects_archived_namespace_like_java() -> None:
    connection = FakeWithdrawReviewConnection(namespace_status="ARCHIVED")

    with pytest.raises(SkillLifecycleError, match="error.namespace.archived") as exc_info:
        await withdraw_skill_version_review(FakeEngine(connection), withdraw_input())

    assert exc_info.value.status_code == 400
    assert not any("DELETE FROM review_task" in statement for statement in connection.statements)
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


def test_withdraw_skill_version_review_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[SkillVersionWithdrawReviewInput] = []

    async def withdrawer(lifecycle_input: SkillVersionWithdrawReviewInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": 42, "action": "WITHDRAW_REVIEW", "status": "UPLOADED"}

    app.state.skill_withdraw_review_writer = withdrawer
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/versions/1.1.0/withdraw-review",
        headers={"X-Mock-User-Id": "publisher", "X-Request-Id": "withdraw-version-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["requestId"] == "withdraw-version-test"
    assert body["data"]["action"] == "WITHDRAW_REVIEW"
    assert body["data"]["status"] == "UPLOADED"
    assert seen[0].namespace == "team-a"
    assert seen[0].version == "1.1.0"
    assert seen[0].user_id == "publisher"


def test_withdraw_skill_version_review_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post("/api/v1/skills/team-a/agent-helper/versions/1.1.0/withdraw-review").status_code == 401
