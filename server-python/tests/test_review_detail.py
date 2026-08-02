from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.query import read_review_detail


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []


class FakeReviewDetailConnection:
    def __init__(
        self,
        *,
        submitted_by: str = "submitter",
        namespace_type: str = "TEAM",
        platform_roles: list[str] | None = None,
        namespace_role: str | None = None,
        missing_task: bool = False,
        archived_task: bool = False,
    ) -> None:
        self.submitted_by = submitted_by
        self.namespace_type = namespace_type
        self.platform_roles = platform_roles or []
        self.namespace_role = namespace_role
        self.missing_task = missing_task
        self.archived_task = archived_task
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM review_task rt" in sql:
            if self.missing_task:
                return FakeResult(row=None)
            return FakeResult(
                row={
                    "id": 801,
                    "skill_version_id": 52,
                    "namespace_id": 20,
                    "status": "PENDING",
                    "submitted_by": self.submitted_by,
                    "submitted_by_name": "Submitter",
                    "reviewed_by": None,
                    "reviewed_by_name": None,
                    "review_comment": None,
                    "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    "reviewed_at": None,
                    "namespace_slug": "team-a",
                    "namespace_type": self.namespace_type,
                    "skill_slug": "agent-helper",
                    "version_name": "1.0.0",
                    "version_status": "PENDING_REVIEW",
                }
            )
        if "FROM review_attempt_archive raa" in sql:
            if not self.archived_task:
                return FakeResult(row=None)
            return FakeResult(
                row={
                    "id": 801,
                    "skill_version_id": 52,
                    "namespace_id": 20,
                    "status": "REJECTED",
                    "submitted_by": self.submitted_by,
                    "submitted_by_name": "Submitter",
                    "reviewed_by": "reviewer",
                    "reviewed_by_name": "Reviewer",
                    "review_comment": "Fix the manifest",
                    "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    "reviewed_at": datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
                    "namespace_slug": "team-a",
                    "namespace_type": self.namespace_type,
                    "skill_slug": "agent-helper",
                    "version_name": "1.0.0",
                    "version_status": "REJECTED",
                    "parsed_metadata_json": {"name": "Agent Helper", "description": "Archived candidate"},
                    "manifest_json": [{"path": "SKILL.md", "size": 12}],
                    "files_json": [
                        {
                            "path": "SKILL.md",
                            "size": 12,
                            "contentType": "text/markdown",
                            "sha256": "archived-sha",
                        }
                    ],
                    "scanner_summary_json": [{"scannerType": "SEMGREP", "verdict": "PASS"}],
                    "replacement_version_id": 53,
                    "replacement_review_task_id": 802,
                    "archived_at": datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "FROM namespace_member" in sql:
            if self.namespace_role is None:
                return FakeResult(rows=[])
            return FakeResult(rows=[{"namespace_id": 20, "role": self.namespace_role}])

        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakeReviewDetailConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewDetailConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewDetailConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


@pytest.mark.anyio
async def test_read_review_detail_allows_submitter() -> None:
    connection = FakeReviewDetailConnection(submitted_by="local-user", namespace_role=None)

    response = await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="local-user")

    assert response["id"] == 801
    assert response["submittedBy"] == "local-user"
    assert response["namespace"] == "team-a"
    assert response["versionStatus"] == "PENDING_REVIEW"
    assert response["submittedAt"] == "2026-06-09T10:00:00Z"
    assert response["superseded"] is False
    assert response["artifactAvailable"] is True


@pytest.mark.anyio
async def test_read_review_detail_allows_namespace_admin_for_non_global_namespace() -> None:
    connection = FakeReviewDetailConnection(submitted_by="submitter", namespace_role="ADMIN")

    response = await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="team-admin")

    assert response["id"] == 801
    assert response["submittedBy"] == "submitter"


@pytest.mark.anyio
async def test_read_review_detail_forbids_unrelated_user() -> None:
    connection = FakeReviewDetailConnection(submitted_by="submitter", namespace_role="MEMBER")

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="member")


@pytest.mark.anyio
async def test_read_review_detail_forbids_namespace_admin_on_global_namespace() -> None:
    connection = FakeReviewDetailConnection(submitted_by="submitter", namespace_type="GLOBAL", namespace_role="ADMIN")

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="global-admin")


@pytest.mark.anyio
async def test_read_review_detail_returns_not_found_for_missing_task() -> None:
    connection = FakeReviewDetailConnection(missing_task=True)

    with pytest.raises(ValueError, match="review_task.not_found"):
        await read_review_detail(FakeEngine(connection), review_task_id=999, user_id="local-user")


@pytest.mark.anyio
async def test_read_review_detail_falls_back_to_archived_attempt_for_submitter() -> None:
    connection = FakeReviewDetailConnection(
        submitted_by="local-user",
        namespace_role=None,
        missing_task=True,
        archived_task=True,
    )

    response = await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="local-user")

    assert response["id"] == 801
    assert response["skillVersionId"] == 52
    assert response["status"] == "REJECTED"
    assert response["reviewComment"] == "Fix the manifest"
    assert response["superseded"] is True
    assert response["artifactAvailable"] is False
    assert response["replacementVersionId"] == 53
    assert response["replacementReviewTaskId"] == 802
    assert response["archivedAt"] == "2026-06-10T09:00:00Z"
    assert response["archivedSnapshot"]["files"] == [
        {
            "path": "SKILL.md",
            "size": 12,
            "contentType": "text/markdown",
            "sha256": "archived-sha",
        }
    ]
    assert response["archivedSnapshot"]["scannerSummary"][0]["scannerType"] == "SEMGREP"


@pytest.mark.anyio
async def test_read_review_detail_falls_back_to_archived_attempt_for_namespace_admin() -> None:
    connection = FakeReviewDetailConnection(
        namespace_role="ADMIN",
        missing_task=True,
        archived_task=True,
    )

    response = await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="team-admin")

    assert response["superseded"] is True


@pytest.mark.anyio
async def test_read_review_detail_forbids_unrelated_user_from_archived_attempt() -> None:
    connection = FakeReviewDetailConnection(
        namespace_role="MEMBER",
        missing_task=True,
        archived_task=True,
    )

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_detail(FakeEngine(connection), review_task_id=801, user_id="member")


def test_review_detail_route_returns_java_read_envelope() -> None:
    app = create_app()
    seen: list[tuple[int, str]] = []

    async def reader(review_task_id: int, user_id: str) -> dict[str, object]:
        seen.append((review_task_id, user_id))
        return {
            "id": review_task_id,
            "skillVersionId": 52,
            "namespace": "team-a",
            "skillSlug": "agent-helper",
            "version": "1.0.0",
            "status": "PENDING",
            "submittedBy": user_id,
            "submittedByName": "Local User",
            "reviewedBy": None,
            "reviewedByName": None,
            "reviewComment": None,
            "submittedAt": "2026-06-09T10:00:00Z",
            "reviewedAt": None,
        }

    app.state.review_detail_reader = reader
    client = TestClient(app)

    response = client.get(
        "/api/web/reviews/801",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "review-detail-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert body["requestId"] == "review-detail-test"
    assert body["data"]["id"] == 801
    assert seen == [(801, "local-user")]


def test_review_detail_route_requires_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/reviews/801")

    assert response.status_code == 401
