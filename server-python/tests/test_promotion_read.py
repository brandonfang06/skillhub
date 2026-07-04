from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.promotion.query import PromotionListQuery, PromotionQueryError, list_pending_promotions, list_promotions, read_promotion_detail


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


class FakePromotionConnection:
    def __init__(
        self,
        *,
        platform_roles: list[str] | None = None,
        submitted_by: str = "submitter",
        missing_request: bool = False,
    ) -> None:
        self.platform_roles = platform_roles or []
        self.submitted_by = submitted_by
        self.missing_request = missing_request
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "COUNT(*)" in sql and "FROM promotion_request pr" in sql:
            return FakeResult(scalar=7)
        if "FROM promotion_request pr" in sql:
            if self.missing_request and "WHERE pr.id" in sql:
                return FakeResult(row=None)
            row = {
                "id": 301,
                "source_skill_id": 101,
                "source_skill_display_name": "Agent Helper",
                "source_skill_summary": "Helps agents complete routine work.",
                "source_namespace": "team-a",
                "skill_slug": "agent-helper",
                "version_name": "1.0.0",
                "source_version_file_count": 3,
                "source_version_total_size": 2048,
                "source_skill_download_count": 7,
                "source_skill_star_count": 2,
                "target_namespace": "global",
                "target_skill_id": None,
                "status": "PENDING",
                "submitted_by": self.submitted_by,
                "submitted_by_name": "Submitter",
                "reviewed_by": None,
                "reviewed_by_name": None,
                "review_comment": None,
                "submitted_at": datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
                "reviewed_at": None,
            }
            if "WHERE pr.id" in sql:
                return FakeResult(row=row)
            return FakeResult(rows=[row])

        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakePromotionConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakePromotionConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakePromotionConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


@pytest.mark.anyio
async def test_list_promotions_requires_platform_review_role_and_preserves_page_contract() -> None:
    connection = FakePromotionConnection(platform_roles=["SKILL_ADMIN"])

    response = await list_promotions(
        FakeEngine(connection),
        PromotionListQuery(status="pending", page=1, size=3, user_id="admin"),
    )

    assert response["total"] == 7
    assert response["page"] == 1
    assert response["size"] == 3
    assert response["items"][0] == {
        "id": 301,
        "sourceSkillId": 101,
        "sourceSkillDisplayName": "Agent Helper",
        "sourceSkillSummary": "Helps agents complete routine work.",
        "sourceNamespace": "team-a",
        "sourceSkillSlug": "agent-helper",
        "sourceVersion": "1.0.0",
        "sourceVersionFileCount": 3,
        "sourceVersionTotalSize": 2048,
        "sourceSkillDownloadCount": 7,
        "sourceSkillStarCount": 2,
        "targetNamespace": "global",
        "targetSkillId": None,
        "status": "PENDING",
        "submittedBy": "submitter",
        "submittedByName": "Submitter",
        "reviewedBy": None,
        "reviewedByName": None,
        "reviewComment": None,
        "submittedAt": "2026-06-09T11:00:00Z",
        "reviewedAt": None,
    }
    page_index = next(index for index, sql in enumerate(connection.statements) if "ORDER BY pr.submitted_at" in sql)
    assert connection.params[page_index]["status"] == "PENDING"
    assert connection.params[page_index]["limit"] == 3
    assert connection.params[page_index]["offset"] == 3


@pytest.mark.anyio
async def test_list_promotions_history_supports_reviewed_at_sorting() -> None:
    desc = FakePromotionConnection(platform_roles=["SKILL_ADMIN"])
    asc = FakePromotionConnection(platform_roles=["SKILL_ADMIN"])

    await list_promotions(
        FakeEngine(desc),
        PromotionListQuery(
            status="APPROVED",
            page=0,
            size=10,
            user_id="admin",
            sort_by="reviewedAt",
            sort_direction="DESC",
        ),
    )
    await list_promotions(
        FakeEngine(asc),
        PromotionListQuery(
            status="REJECTED",
            page=0,
            size=10,
            user_id="admin",
            sort_by="reviewedAt",
            sort_direction="ASC",
        ),
    )

    desc_sql = next(sql for sql in desc.statements if "FROM promotion_request pr" in sql and "ORDER BY" in sql)
    asc_sql = next(sql for sql in asc.statements if "FROM promotion_request pr" in sql and "ORDER BY" in sql)
    assert "pr.reviewed_at DESC" in desc_sql
    assert "pr.id DESC" in desc_sql
    assert "pr.reviewed_at ASC" in asc_sql
    assert "pr.id ASC" in asc_sql


@pytest.mark.anyio
async def test_list_promotions_rejects_invalid_status_and_sort_parameters() -> None:
    connection = FakePromotionConnection(platform_roles=["SKILL_ADMIN"])

    with pytest.raises(PromotionQueryError, match="promotion.status.invalid"):
        await list_promotions(
            FakeEngine(connection),
            PromotionListQuery(status="", page=0, size=20, user_id="admin"),
        )

    with pytest.raises(PromotionQueryError, match="promotion.sort.pending_unsupported"):
        await list_promotions(
            FakeEngine(connection),
            PromotionListQuery(status="PENDING", page=0, size=20, user_id="admin", sort_by="reviewedAt"),
        )

    with pytest.raises(PromotionQueryError, match="promotion.sort.field.invalid"):
        await list_promotions(
            FakeEngine(connection),
            PromotionListQuery(status="APPROVED", page=0, size=20, user_id="admin", sort_by="submittedAt"),
        )

    with pytest.raises(PromotionQueryError, match="promotion.sort.direction.invalid"):
        await list_promotions(
            FakeEngine(connection),
            PromotionListQuery(
                status="APPROVED",
                page=0,
                size=20,
                user_id="admin",
                sort_by="reviewedAt",
                sort_direction="SIDEWAYS",
            ),
        )


@pytest.mark.anyio
async def test_list_promotions_forbids_non_platform_reviewer() -> None:
    connection = FakePromotionConnection(platform_roles=[])

    with pytest.raises(ValueError, match="promotion.no_permission"):
        await list_promotions(
            FakeEngine(connection),
            PromotionListQuery(status="PENDING", page=0, size=20, user_id="local-user"),
        )

    assert not any("FROM promotion_request pr" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_list_pending_promotions_uses_pending_status() -> None:
    connection = FakePromotionConnection(platform_roles=["SUPER_ADMIN"])

    response = await list_pending_promotions(FakeEngine(connection), page=0, size=10, user_id="admin")

    assert response["total"] == 7
    page_index = next(index for index, sql in enumerate(connection.statements) if "ORDER BY pr.submitted_at" in sql)
    assert connection.params[page_index]["status"] == "PENDING"
    assert connection.params[page_index]["limit"] == 10


@pytest.mark.anyio
async def test_read_promotion_detail_allows_submitter() -> None:
    connection = FakePromotionConnection(platform_roles=[], submitted_by="local-user")

    response = await read_promotion_detail(FakeEngine(connection), promotion_id=301, user_id="local-user")

    assert response["id"] == 301
    assert response["submittedBy"] == "local-user"
    assert response["sourceNamespace"] == "team-a"


@pytest.mark.anyio
async def test_read_promotion_detail_allows_platform_reviewer_and_forbids_unrelated_user() -> None:
    allowed = FakePromotionConnection(platform_roles=["SKILL_ADMIN"], submitted_by="submitter")
    denied = FakePromotionConnection(platform_roles=[], submitted_by="submitter")

    response = await read_promotion_detail(FakeEngine(allowed), promotion_id=301, user_id="admin")

    assert response["id"] == 301
    with pytest.raises(ValueError, match="promotion.no_permission"):
        await read_promotion_detail(FakeEngine(denied), promotion_id=301, user_id="member")


@pytest.mark.anyio
async def test_read_promotion_detail_returns_not_found_for_missing_request() -> None:
    connection = FakePromotionConnection(platform_roles=["SKILL_ADMIN"], missing_request=True)

    with pytest.raises(ValueError, match="promotion.not_found"):
        await read_promotion_detail(FakeEngine(connection), promotion_id=999, user_id="admin")


def test_promotion_read_routes_return_java_envelopes_and_forward_inputs() -> None:
    app = create_app()
    seen: list[tuple[str, dict[str, object]]] = []

    async def list_reader(**kwargs: object) -> dict[str, object]:
        seen.append(("list", kwargs))
        return {"items": [], "total": 0, "page": kwargs["page"], "size": kwargs["size"]}

    async def pending_reader(**kwargs: object) -> dict[str, object]:
        seen.append(("pending", kwargs))
        return {"items": [], "total": 0, "page": kwargs["page"], "size": kwargs["size"]}

    async def detail_reader(promotion_id: int, user_id: str) -> dict[str, object]:
        seen.append(("detail", {"promotion_id": promotion_id, "user_id": user_id}))
        return {"id": promotion_id, "sourceSkillId": 101, "sourceSkillSlug": "agent-helper", "status": "PENDING"}

    app.state.promotion_list_reader = list_reader
    app.state.promotion_pending_reader = pending_reader
    app.state.promotion_detail_reader = detail_reader
    client = TestClient(app)

    listed = client.get(
        "/api/v1/promotions?status=APPROVED&page=2&size=4&sortBy=reviewedAt&sortDirection=ASC",
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "promotion-list-test"},
    )
    pending = client.get("/api/web/promotions/pending?page=1", headers={"X-Mock-User-Id": "admin"})
    detail = client.get("/api/web/promotions/301", headers={"X-Mock-User-Id": "submitter"})

    assert listed.status_code == 200
    assert listed.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert listed.json()["requestId"] == "promotion-list-test"
    assert pending.status_code == 200
    assert detail.status_code == 200
    assert seen == [
        ("list", {"status": "APPROVED", "page": 2, "size": 4, "sort_by": "reviewedAt", "sort_direction": "ASC", "user_id": "admin"}),
        ("pending", {"page": 1, "size": 20, "user_id": "admin"}),
        ("detail", {"promotion_id": 301, "user_id": "submitter"}),
    ]


def test_promotion_read_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.get("/api/v1/promotions").status_code == 401
    assert client.get("/api/v1/promotions/pending").status_code == 401
    assert client.get("/api/v1/promotions/301").status_code == 401
