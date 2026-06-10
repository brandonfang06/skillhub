from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.review_reports import (
    AdminReviewReportError,
    list_admin_profile_reviews,
    list_admin_skill_reports,
)
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: int | None = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        if self.scalar is None:
            raise AssertionError("scalar value was not provided")
        return self.scalar


class FakeTransaction:
    def __init__(self, connection: "FakeReviewReportConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeReviewReportConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeReviewReportConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeReviewReportConnection:
    def __init__(self) -> None:
        self.skill_reports = [
            {
                "id": 2,
                "skill_id": 20,
                "namespace": None,
                "skill_slug": None,
                "skill_display_name": None,
                "reporter_id": "reporter-2",
                "reason": "Abuse",
                "details": None,
                "status": "PENDING",
                "handled_by": None,
                "handle_comment": None,
                "created_at": datetime(2026, 6, 10, 8, 2, tzinfo=UTC),
                "handled_at": None,
            },
            {
                "id": 1,
                "skill_id": 10,
                "namespace": "team-a",
                "skill_slug": "skill-a",
                "skill_display_name": "Skill A",
                "reporter_id": "reporter-1",
                "reason": "Spam",
                "details": "details",
                "status": "PENDING",
                "handled_by": None,
                "handle_comment": None,
                "created_at": datetime(2026, 6, 10, 8, 1, tzinfo=UTC),
                "handled_at": None,
            },
        ]
        self.profile_reviews = [
            {
                "id": 3,
                "user_id": "user-3",
                "submitter_name": "Current User 3",
                "changes": "{invalid",
                "old_values": "{also-invalid",
                "status": "PENDING",
                "machine_result": "PASS",
                "reviewer_id": None,
                "reviewer_name": None,
                "review_comment": None,
                "created_at": datetime(2026, 6, 10, 9, 3, tzinfo=UTC),
                "reviewed_at": None,
            },
            {
                "id": 1,
                "user_id": "user-1",
                "submitter_name": "Newest Name",
                "changes": {"displayName": "New Name"},
                "old_values": {"displayName": "Old Name"},
                "status": "APPROVED",
                "machine_result": "PASS",
                "reviewer_id": "admin-1",
                "reviewer_name": "Admin Reviewer",
                "review_comment": None,
                "created_at": datetime(2026, 6, 10, 9, 1, tzinfo=UTC),
                "reviewed_at": datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            },
        ]

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM skill_report" in sql:
            rows = [row.copy() for row in self.skill_reports if row["status"] == bound["status"]]
            rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
            if "COUNT(*)" in sql:
                return FakeResult(scalar=len(rows))
            return FakeResult(rows=rows[int(bound["offset"]) : int(bound["offset"]) + int(bound["limit"])])
        if "FROM profile_change_request" in sql:
            rows = [row.copy() for row in self.profile_reviews if row["status"] == bound["status"]]
            sort_key = "created_at" if bound["status"] == "PENDING" else "reviewed_at"
            rows.sort(
                key=lambda row: (
                    row[sort_key] or datetime.min.replace(tzinfo=UTC),
                    row["id"],
                ),
                reverse=bound["sort_desc"],
            )
            if "COUNT(*)" in sql:
                return FakeResult(scalar=len(rows))
            return FakeResult(rows=rows[int(bound["offset"]) : int(bound["offset"]) + int(bound["limit"])])
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.anyio
async def test_admin_skill_report_list_projects_java_fields_and_missing_skill_context() -> None:
    response = await list_admin_skill_reports(
        FakeEngine(FakeReviewReportConnection()),
        status=None,
        page=0,
        size=20,
        platform_roles=["SKILL_ADMIN"],
    )

    assert response["total"] == 2
    assert response["page"] == 0
    assert response["size"] == 20
    assert response["items"][0] == {
        "id": 2,
        "skillId": 20,
        "namespace": None,
        "skillSlug": None,
        "skillDisplayName": None,
        "reporterId": "reporter-2",
        "reason": "Abuse",
        "details": None,
        "status": "PENDING",
        "handledBy": None,
        "handleComment": None,
        "createdAt": "2026-06-10T08:02:00Z",
        "handledAt": None,
    }
    assert response["items"][1]["namespace"] == "team-a"
    assert response["items"][1]["skillSlug"] == "skill-a"


@pytest.mark.anyio
async def test_admin_profile_review_list_projects_java_fields_and_json_fallbacks() -> None:
    pending = await list_admin_profile_reviews(
        FakeEngine(FakeReviewReportConnection()),
        status=" ",
        page=0,
        size=20,
        sort_direction="DESC",
        platform_roles=["USER_ADMIN"],
    )

    assert pending["total"] == 1
    assert pending["items"][0] == {
        "id": 3,
        "userId": "user-3",
        "username": "Current User 3",
        "currentDisplayName": "Current User 3",
        "requestedDisplayName": None,
        "status": "PENDING",
        "machineResult": "PASS",
        "reviewerId": None,
        "reviewerName": None,
        "reviewComment": None,
        "createdAt": "2026-06-10T09:03:00Z",
        "reviewedAt": None,
    }

    approved = await list_admin_profile_reviews(
        FakeEngine(FakeReviewReportConnection()),
        status="approved",
        page=0,
        size=20,
        sort_direction="ASC",
        platform_roles=["SUPER_ADMIN"],
    )

    assert approved["items"][0]["username"] == "Newest Name"
    assert approved["items"][0]["currentDisplayName"] == "Old Name"
    assert approved["items"][0]["requestedDisplayName"] == "New Name"
    assert approved["items"][0]["reviewerName"] == "Admin Reviewer"


@pytest.mark.anyio
async def test_admin_review_report_lists_require_expected_roles_and_statuses() -> None:
    engine = FakeEngine(FakeReviewReportConnection())

    with pytest.raises(AdminReviewReportError, match="error.admin.skillReport.readDenied"):
        await list_admin_skill_reports(engine, status="PENDING", page=0, size=20, platform_roles=["USER"])
    with pytest.raises(AdminReviewReportError, match="error.profileReview.readDenied"):
        await list_admin_profile_reviews(engine, status="PENDING", page=0, size=20, sort_direction="DESC", platform_roles=["USER"])
    with pytest.raises(AdminReviewReportError, match="error.skill.report.status.invalid"):
        await list_admin_skill_reports(engine, status="bad", page=0, size=20, platform_roles=["SUPER_ADMIN"])
    with pytest.raises(AdminReviewReportError, match="error.profileReview.status.invalid"):
        await list_admin_profile_reviews(engine, status="bad", page=0, size=20, sort_direction="DESC", platform_roles=["SUPER_ADMIN"])


def test_admin_review_report_routes_use_read_envelopes_and_get_only_roles() -> None:
    app = create_app()
    captured: dict[str, dict[str, Any]] = {}
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": {
            "skill-admin": ["SKILL_ADMIN"],
            "user-admin": ["USER_ADMIN"],
            "super-admin": ["SUPER_ADMIN"],
        }.get(user_id, ["USER"]),
    }
    app.state.admin_skill_report_reader = lambda payload, user: captured.setdefault(
        "skill_reports",
        {"items": [{"id": 1}], "total": 1, "page": payload["page"], "size": payload["size"], "status": payload["status"]},
    )
    app.state.admin_profile_review_reader = lambda payload, user: captured.setdefault(
        "profile_reviews",
        {"items": [{"id": 2}], "total": 1, "page": payload["page"], "size": payload["size"], "sortDirection": payload["sortDirection"]},
    )
    client = TestClient(app)

    assert client.get("/api/v1/admin/skill-reports").status_code == 401
    assert client.get("/api/v1/admin/skill-reports", headers={"X-Mock-User-Id": "user"}).status_code == 403
    skill_response = client.get("/api/v1/admin/skill-reports?status=pending&page=1&size=5", headers={"X-Mock-User-Id": "skill-admin"})
    assert skill_response.status_code == 200
    assert skill_response.json()["msg"] == "\u6210\u529f"
    assert skill_response.json()["data"] == {"items": [{"id": 1}], "total": 1, "page": 1, "size": 5, "status": "pending"}

    assert client.get("/api/v1/admin/profile-reviews", headers={"X-Mock-User-Id": "skill-admin"}).status_code == 403
    profile_response = client.get(
        "/api/v1/admin/profile-reviews?status=approved&page=2&size=7&sortDirection=ASC",
        headers={"X-Mock-User-Id": "user-admin"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["msg"] == "\u6210\u529f"
    assert profile_response.json()["data"] == {"items": [{"id": 2}], "total": 1, "page": 2, "size": 7, "sortDirection": "ASC"}
