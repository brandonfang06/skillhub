from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.query import ReviewListQuery, list_my_review_submissions, list_pending_reviews, list_review_tasks


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


class FakeReviewListConnection:
    def __init__(self, *, platform_roles: list[str] | None = None, namespace_role: str | None = "ADMIN") -> None:
        self.platform_roles = platform_roles or []
        self.namespace_role = namespace_role
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []
        self.task_rows = [
            {
                "id": 1001,
                "skill_version_id": 501,
                "namespace_id": 20,
                "status": "PENDING",
                "submitted_by": "submitter-a",
                "submitted_by_name": "Submitter A",
                "reviewed_by": None,
                "reviewed_by_name": None,
                "review_comment": None,
                "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                "reviewed_at": None,
                "namespace_slug": "team-a",
                "namespace_type": "TEAM",
                "skill_slug": "agent-helper",
                "version_name": "1.0.0",
            }
        ]

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "FROM namespace_member" in sql and "WHERE user_id" in sql:
            if self.namespace_role is None:
                return FakeResult(rows=[])
            return FakeResult(rows=[{"namespace_id": 20, "role": self.namespace_role}])
        if "FROM namespace" in sql:
            return FakeResult(row={"id": 20, "type": "TEAM", "status": "ACTIVE"})
        if "COUNT(*)" in sql and "FROM review_task rt" in sql:
            return FakeResult(scalar=42)
        if "FROM review_task rt" in sql:
            return FakeResult(rows=self.task_rows)

        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakeReviewListConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewListConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewListConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


@pytest.mark.anyio
async def test_list_review_tasks_global_queue_requires_platform_role_and_preserves_total() -> None:
    connection = FakeReviewListConnection(platform_roles=["SKILL_ADMIN"], namespace_role=None)

    response = await list_review_tasks(
        FakeEngine(connection),
        ReviewListQuery(status="approved", namespace_id=None, page=1, size=5, sort_direction="ASC", user_id="admin"),
    )

    assert response["total"] == 42
    assert response["page"] == 1
    assert response["size"] == 5
    assert response["items"][0]["id"] == 1001
    assert response["items"][0]["namespace"] == "team-a"
    count_index = next(index for index, sql in enumerate(connection.statements) if "COUNT(*)" in sql)
    page_index = next(index for index, sql in enumerate(connection.statements) if "ORDER BY" in sql)
    assert count_index < page_index
    assert connection.params[page_index]["status"] == "APPROVED"
    assert connection.params[page_index]["limit"] == 5
    assert connection.params[page_index]["offset"] == 5
    assert "reviewed_at ASC" in connection.statements[page_index]


@pytest.mark.anyio
async def test_list_review_tasks_forbids_global_queue_without_platform_role() -> None:
    connection = FakeReviewListConnection(platform_roles=[], namespace_role="ADMIN")

    with pytest.raises(ValueError, match="review.no_permission"):
        await list_review_tasks(
            FakeEngine(connection),
            ReviewListQuery(status="PENDING", namespace_id=None, page=0, size=20, sort_direction="DESC", user_id="team-admin"),
        )

    assert not any("FROM review_task rt" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_list_pending_reviews_uses_namespace_permission_and_pending_status() -> None:
    connection = FakeReviewListConnection(platform_roles=[], namespace_role="OWNER")

    response = await list_pending_reviews(FakeEngine(connection), namespace_id=20, page=0, size=20, user_id="owner")

    assert response["total"] == 42
    page_index = next(index for index, sql in enumerate(connection.statements) if "FROM review_task rt" in sql and "ORDER BY" in sql)
    assert connection.params[page_index]["namespace_id"] == 20
    assert connection.params[page_index]["status"] == "PENDING"


@pytest.mark.anyio
async def test_list_my_review_submissions_filters_submitter_and_pending_status() -> None:
    connection = FakeReviewListConnection(platform_roles=[], namespace_role=None)

    response = await list_my_review_submissions(FakeEngine(connection), page=0, size=20, user_id="submitter-a")

    assert response["items"][0]["submittedBy"] == "submitter-a"
    page_index = next(index for index, sql in enumerate(connection.statements) if "FROM review_task rt" in sql and "ORDER BY" in sql)
    assert connection.params[page_index]["submitted_by"] == "submitter-a"
    assert connection.params[page_index]["status"] == "PENDING"


def test_review_list_route_returns_java_read_envelope() -> None:
    app = create_app()
    seen: list[dict[str, object]] = []

    async def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return {"items": [], "total": 0, "page": kwargs["page"], "size": kwargs["size"]}

    app.state.review_list_reader = reader
    client = TestClient(app)

    response = client.get(
        "/api/v1/reviews?status=PENDING&page=1&size=5&sortDirection=ASC",
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "review-list-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert body["requestId"] == "review-list-test"
    assert body["data"] == {"items": [], "total": 0, "page": 1, "size": 5}
    assert seen[0]["status"] == "PENDING"
    assert seen[0]["sort_direction"] == "ASC"


def test_review_pending_and_my_submissions_routes_forward_reader_inputs() -> None:
    app = create_app()
    seen: list[tuple[str, dict[str, object]]] = []

    async def pending_reader(**kwargs: object) -> dict[str, object]:
        seen.append(("pending", kwargs))
        return {"items": [], "total": 0, "page": kwargs["page"], "size": kwargs["size"]}

    async def submissions_reader(**kwargs: object) -> dict[str, object]:
        seen.append(("submissions", kwargs))
        return {"items": [], "total": 0, "page": kwargs["page"], "size": kwargs["size"]}

    app.state.review_pending_reader = pending_reader
    app.state.review_my_submissions_reader = submissions_reader
    client = TestClient(app)

    pending = client.get("/api/web/reviews/pending?namespaceId=20", headers={"X-Mock-User-Id": "owner"})
    submissions = client.get("/api/web/reviews/my-submissions?page=2&size=10", headers={"X-Mock-User-Id": "owner"})

    assert pending.status_code == 200
    assert submissions.status_code == 200
    assert seen[0] == ("pending", {"namespace_id": 20, "page": 0, "size": 20, "user_id": "owner"})
    assert seen[1] == ("submissions", {"page": 2, "size": 10, "user_id": "owner"})


def test_review_list_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/reviews?status=PENDING")

    assert response.status_code == 401
