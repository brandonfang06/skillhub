from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.governance.workbench import (
    ACTIVITY_ACTIONS,
    GovernanceWorkbenchError,
    get_governance_summary,
    list_governance_activity,
    list_governance_inbox,
    list_governance_notifications,
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
        if self.scalar is not None:
            return self.scalar
        return int(self.rows[0]["count"])


class FakeTransaction:
    def __init__(self, connection: "FakeGovernanceConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeGovernanceConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeGovernanceConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeGovernanceConnection:
    def __init__(self) -> None:
        self.platform_roles: dict[str, list[str]] = {
            "skill-admin": ["SKILL_ADMIN"],
            "auditor": ["AUDITOR"],
            "namespace-admin": [],
            "regular-user": [],
        }
        self.namespace_roles = {"namespace-admin": [{"namespace_id": 10, "role": "ADMIN"}]}
        self.summary_counts = {
            "all_reviews": 3,
            "namespace_reviews": 1,
            "promotions": 2,
            "reports": 1,
            "unread": 4,
        }
        self.review_rows = [
            {
                "type": "REVIEW",
                "id": 11,
                "title": "team-scope/review-skill@1.0.0",
                "subtitle": "Pending review",
                "timestamp": datetime(2026, 6, 10, 8, 5, tzinfo=UTC),
                "namespace": "team-scope",
                "skill_slug": "review-skill",
            }
        ]
        self.promotion_rows = [
            {
                "type": "PROMOTION",
                "id": 21,
                "title": "source-scope/promo-skill@2.0.0",
                "subtitle": "Promote to @global",
                "timestamp": datetime(2026, 6, 10, 8, 6, tzinfo=UTC),
                "namespace": "source-scope",
                "skill_slug": "promo-skill",
            }
        ]
        self.report_rows = [
            {
                "type": "REPORT",
                "id": 31,
                "title": "report-scope/reported-skill",
                "subtitle": "bad content",
                "timestamp": datetime(2026, 6, 10, 8, 7, tzinfo=UTC),
                "namespace": "report-scope",
                "skill_slug": "reported-skill",
            }
        ]
        self.activity_rows = [
            {
                "id": 41,
                "action": "REVIEW_APPROVE",
                "actor_user_id": "skill-admin",
                "display_name": "Skill Admin",
                "detail_json": '{"comment":"ok"}',
                "target_type": "REVIEW",
                "target_id": 11,
                "created_at": datetime(2026, 6, 10, 8, 8, tzinfo=UTC),
            }
        ]
        self.notification_rows = [
            {
                "id": 51,
                "category": "REVIEW",
                "entity_type": "REVIEW",
                "entity_id": 11,
                "title": "Review needed",
                "body_json": '{"skill":"review-skill"}',
                "status": "UNREAD",
                "created_at": datetime(2026, 6, 10, 8, 9, tzinfo=UTC),
                "read_at": None,
            }
        ]
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.params.append(bound)
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": code} for code in self.platform_roles.get(str(bound["user_id"]), [])])
        if "FROM namespace_member" in sql:
            return FakeResult(rows=self.namespace_roles.get(str(bound["user_id"]), []))
        if "COUNT(*)" in sql and "FROM review_task" in sql and "namespace_id IN" in sql:
            return FakeResult(scalar=self.summary_counts["namespace_reviews"])
        if "COUNT(*)" in sql and "FROM review_task" in sql:
            return FakeResult(scalar=self.summary_counts["all_reviews"])
        if "COUNT(*)" in sql and "FROM promotion_request" in sql:
            return FakeResult(scalar=self.summary_counts["promotions"])
        if "COUNT(*)" in sql and "FROM skill_report" in sql:
            return FakeResult(scalar=self.summary_counts["reports"])
        if "COUNT(*)" in sql and "FROM user_notification" in sql and "status = 'UNREAD'" in sql:
            return FakeResult(scalar=self.summary_counts["unread"])
        if "review_inbox" in sql:
            return FakeResult(rows=self.review_rows)
        if "promotion_inbox" in sql:
            return FakeResult(rows=self.promotion_rows)
        if "report_inbox" in sql:
            return FakeResult(rows=self.report_rows)
        if "COUNT(*)" in sql and "FROM audit_log" in sql:
            assert set(bound["actions"]) == ACTIVITY_ACTIONS
            return FakeResult(scalar=len(self.activity_rows))
        if "FROM audit_log" in sql:
            return FakeResult(rows=self.activity_rows)
        if "COUNT(*)" in sql and "FROM user_notification" in sql:
            return FakeResult(scalar=len(self.notification_rows))
        if "FROM user_notification" in sql:
            return FakeResult(rows=self.notification_rows)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.anyio
async def test_summary_scopes_counts_by_platform_or_namespace_roles() -> None:
    connection = FakeGovernanceConnection()

    platform = await get_governance_summary(FakeEngine(connection), user_id="skill-admin")
    namespace = await get_governance_summary(FakeEngine(connection), user_id="namespace-admin")

    assert platform == {
        "pendingReviews": 3,
        "pendingPromotions": 2,
        "pendingReports": 1,
        "unreadNotifications": 4,
    }
    assert namespace == {
        "pendingReviews": 1,
        "pendingPromotions": 0,
        "pendingReports": 0,
        "unreadNotifications": 4,
    }


@pytest.mark.anyio
async def test_inbox_merges_items_by_visibility_type_and_timestamp() -> None:
    connection = FakeGovernanceConnection()

    all_items = await list_governance_inbox(FakeEngine(connection), user_id="skill-admin", type_filter=None, page=0, size=20)
    review_only = await list_governance_inbox(
        FakeEngine(connection),
        user_id="namespace-admin",
        type_filter="review",
        page=0,
        size=20,
    )

    assert all_items["total"] == 6
    assert [item["type"] for item in all_items["items"]] == ["REPORT", "PROMOTION", "REVIEW"]
    assert all_items["items"][0]["timestamp"] == "2026-06-10T08:07:00Z"
    assert review_only["total"] == 1
    assert review_only["items"][0]["type"] == "REVIEW"

    with pytest.raises(GovernanceWorkbenchError, match="error.governance.inbox.type.invalid"):
        await list_governance_inbox(FakeEngine(connection), user_id="skill-admin", type_filter="UNKNOWN", page=0, size=20)


@pytest.mark.anyio
async def test_activity_is_visible_to_platform_governance_or_auditor_only() -> None:
    connection = FakeGovernanceConnection()

    activity = await list_governance_activity(FakeEngine(connection), user_id="auditor", page=0, size=20)
    forbidden_empty = await list_governance_activity(FakeEngine(connection), user_id="regular-user", page=1, size=5)

    assert activity["total"] == 1
    assert activity["items"][0] == {
        "id": 41,
        "action": "REVIEW_APPROVE",
        "actorUserId": "skill-admin",
        "actorDisplayName": "Skill Admin",
        "targetType": "REVIEW",
        "targetId": "11",
        "details": '{"comment":"ok"}',
        "timestamp": "2026-06-10T08:08:00Z",
    }
    assert forbidden_empty == {"items": [], "total": 0, "page": 1, "size": 5}


@pytest.mark.anyio
async def test_governance_notifications_read_legacy_user_notification_table() -> None:
    connection = FakeGovernanceConnection()

    response = await list_governance_notifications(FakeEngine(connection), user_id="skill-admin", page=0, size=20)

    assert response == {
        "items": [
            {
                "id": 51,
                "category": "REVIEW",
                "entityType": "REVIEW",
                "entityId": 11,
                "title": "Review needed",
                "bodyJson": '{"skill":"review-skill"}',
                "status": "UNREAD",
                "createdAt": "2026-06-10T08:09:00Z",
                "readAt": None,
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def test_governance_routes_use_read_envelopes_and_keep_mark_read_unowned() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SKILL_ADMIN"],
    }
    app.state.governance_summary_reader = lambda user_id: {"pendingReviews": 1}
    app.state.governance_inbox_reader = lambda payload, user_id: {"items": [], "total": 0, "page": 0, "size": 20}
    app.state.governance_activity_reader = lambda payload, user_id: {"items": [], "total": 0, "page": 0, "size": 20}
    app.state.governance_notification_reader = lambda payload, user_id: {"items": [], "total": 0, "page": 0, "size": 20}
    client = TestClient(app)

    assert client.get("/api/v1/governance/summary").status_code == 401

    response = client.get("/api/v1/governance/summary", headers={"X-Mock-User-Id": "skill-admin"})
    assert response.status_code == 200
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["data"] == {"pendingReviews": 1}

    web_response = client.get("/api/web/governance/inbox?type=REVIEW", headers={"X-Mock-User-Id": "skill-admin"})
    assert web_response.status_code == 200
    assert web_response.json()["data"]["items"] == []

    assert client.post("/api/v1/governance/notifications/1/read", headers={"X-Mock-User-Id": "skill-admin"}).status_code == 404
