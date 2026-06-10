from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.review_reports import (
    AdminReviewReportError,
    approve_admin_profile_review,
    dismiss_admin_skill_report,
    reject_admin_profile_review,
    resolve_admin_skill_report,
)
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: int | None = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        if self.scalar is not None:
            return self.scalar
        return 1


class FakeTransaction:
    def __init__(self, connection: "FakeMutationConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeMutationConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeMutationConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeMutationConnection:
    def __init__(self) -> None:
        self.skill_reports: dict[int, dict[str, Any]] = {
            10: {"id": 10, "skill_id": 100, "reporter_id": "reporter-1", "status": "PENDING"},
            11: {"id": 11, "skill_id": 101, "reporter_id": "reporter-2", "status": "PENDING"},
            12: {"id": 12, "skill_id": 102, "reporter_id": "reporter-3", "status": "RESOLVED"},
        }
        self.skills: dict[int, dict[str, Any]] = {
            100: {"id": 100, "hidden": False, "status": "ACTIVE"},
            101: {"id": 101, "hidden": False, "status": "ACTIVE"},
        }
        self.profile_reviews: dict[int, dict[str, Any]] = {
            20: {
                "id": 20,
                "user_id": "profile-user",
                "changes": {"displayName": "New Profile"},
                "status": "PENDING",
            },
            21: {
                "id": 21,
                "user_id": "profile-user",
                "changes": {"displayName": "Rejected Profile"},
                "status": "PENDING",
            },
            22: {
                "id": 22,
                "user_id": "profile-user",
                "changes": {"displayName": "Already Done"},
                "status": "APPROVED",
            },
        }
        self.users: dict[str, dict[str, Any]] = {"profile-user": {"id": "profile-user", "display_name": "Old Profile"}}
        self.audit_logs: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        normalized = " ".join(sql.split())
        if "FROM skill_report" in normalized and "WHERE id = :report_id" in normalized:
            row = self.skill_reports.get(int(bound["report_id"]))
            return FakeResult(rows=[row.copy()] if row else [])
        if normalized.startswith("UPDATE skill_report"):
            report = self.skill_reports[int(bound["report_id"])]
            report.update(
                {
                    "status": bound["status"],
                    "handled_by": bound["handled_by"],
                    "handle_comment": bound["handle_comment"],
                    "handled_at": bound["handled_at"],
                }
            )
            return FakeResult()
        if normalized.startswith("UPDATE skill SET hidden"):
            skill = self.skills[int(bound["skill_id"])]
            skill.update({"hidden": True, "hidden_by": bound["actor_user_id"], "updated_by": bound["actor_user_id"]})
            return FakeResult()
        if normalized.startswith("UPDATE skill SET status"):
            skill = self.skills[int(bound["skill_id"])]
            skill.update({"status": "ARCHIVED", "updated_by": bound["actor_user_id"]})
            return FakeResult()
        if normalized.startswith("INSERT INTO audit_log"):
            self.audit_logs.append(dict(bound))
            return FakeResult()
        if normalized.startswith("INSERT INTO user_notification"):
            self.notifications.append(dict(bound))
            return FakeResult()
        if "FROM profile_change_request" in normalized and "WHERE id = :request_id" in normalized:
            row = self.profile_reviews.get(int(bound["request_id"]))
            return FakeResult(rows=[row.copy()] if row else [])
        if "FROM user_account" in normalized and "WHERE id = :user_id" in normalized:
            row = self.users.get(str(bound["user_id"]))
            return FakeResult(rows=[row.copy()] if row else [])
        if normalized.startswith("UPDATE user_account"):
            self.users[str(bound["user_id"])]["display_name"] = bound["display_name"]
            return FakeResult()
        if normalized.startswith("UPDATE profile_change_request"):
            review = self.profile_reviews[int(bound["request_id"])]
            review.update(
                {
                    "status": bound["status"],
                    "reviewer_id": bound["reviewer_id"],
                    "review_comment": bound.get("review_comment"),
                    "reviewed_at": bound["reviewed_at"],
                }
            )
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.anyio
async def test_resolve_skill_report_updates_report_hides_skill_and_writes_side_effects() -> None:
    connection = FakeMutationConnection()
    result = await resolve_admin_skill_report(
        FakeEngine(connection),
        report_id=10,
        actor_user_id="admin-1",
        platform_roles=["SUPER_ADMIN"],
        disposition=" resolve_and_hide ",
        comment="  policy violation  ",
        request_id="req-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
        now=datetime(2026, 6, 10, 10, 0, tzinfo=UTC),
    )

    assert result == {"id": 10, "status": "RESOLVED"}
    assert connection.skill_reports[10]["status"] == "RESOLVED"
    assert connection.skill_reports[10]["handle_comment"] == "policy violation"
    assert connection.skills[100]["hidden"] is True
    assert [entry["action"] for entry in connection.audit_logs] == ["HIDE_SKILL", "RESOLVE_SKILL_REPORT"]
    assert json.loads(connection.audit_logs[0]["detail_json"]) == {"reason": "  policy violation  "}
    assert connection.notifications == [
        {
            "user_id": "reporter-1",
            "category": "REPORT",
            "entity_type": "SKILL_REPORT",
            "entity_id": 10,
            "title": "Report handled",
            "body_json": '{"status":"RESOLVED"}',
            "status": "UNREAD",
            "created_at": datetime(2026, 6, 10, 10, 0, tzinfo=UTC),
        }
    ]


@pytest.mark.anyio
async def test_dismiss_skill_report_updates_report_and_rejects_non_pending() -> None:
    connection = FakeMutationConnection()
    result = await dismiss_admin_skill_report(
        FakeEngine(connection),
        report_id=11,
        actor_user_id="admin-1",
        platform_roles=["SKILL_ADMIN"],
        comment=" ",
        request_id=None,
        client_ip=None,
        user_agent=None,
        now=datetime(2026, 6, 10, 10, 1, tzinfo=UTC),
    )

    assert result == {"id": 11, "status": "DISMISSED"}
    assert connection.skill_reports[11]["handle_comment"] is None
    assert connection.audit_logs[-1]["action"] == "DISMISS_SKILL_REPORT"
    assert connection.notifications[-1]["title"] == "Report dismissed"
    assert connection.notifications[-1]["body_json"] == '{"status":"DISMISSED"}'

    with pytest.raises(AdminReviewReportError, match="error.skill.report.alreadyHandled"):
        await dismiss_admin_skill_report(
            FakeEngine(connection),
            report_id=12,
            actor_user_id="admin-1",
            platform_roles=["SUPER_ADMIN"],
            comment=None,
            request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 10, 2, tzinfo=UTC),
        )


@pytest.mark.anyio
async def test_profile_review_approve_applies_display_name_and_writes_audit() -> None:
    connection = FakeMutationConnection()
    result = await approve_admin_profile_review(
        FakeEngine(connection),
        request_id=20,
        reviewer_id="user-admin",
        platform_roles=["USER_ADMIN"],
        http_request_id="req-approve",
        client_ip="127.0.0.2",
        user_agent="pytest",
        now=datetime(2026, 6, 10, 11, 0, tzinfo=UTC),
    )

    assert result == {"id": 20, "status": "APPROVED"}
    assert connection.profile_reviews[20]["status"] == "APPROVED"
    assert connection.users["profile-user"]["display_name"] == "New Profile"
    assert connection.audit_logs == [
        {
            "actor_user_id": "user-admin",
            "action": "PROFILE_REVIEW_APPROVE",
            "target_type": "PROFILE_CHANGE_REQUEST",
            "target_id": 20,
            "request_id": "req-approve",
            "client_ip": "127.0.0.2",
            "user_agent": "pytest",
            "detail_json": None,
            "created_at": datetime(2026, 6, 10, 11, 0),
        }
    ]


@pytest.mark.anyio
async def test_profile_review_reject_requires_pending_and_writes_comment_detail() -> None:
    connection = FakeMutationConnection()
    result = await reject_admin_profile_review(
        FakeEngine(connection),
        request_id=21,
        reviewer_id="user-admin",
        platform_roles=["SUPER_ADMIN"],
        comment="needs cleanup",
        http_request_id="req-reject",
        client_ip="127.0.0.3",
        user_agent="pytest",
        now=datetime(2026, 6, 10, 11, 1, tzinfo=UTC),
    )

    assert result == {"id": 21, "status": "REJECTED"}
    assert connection.profile_reviews[21]["review_comment"] == "needs cleanup"
    assert json.loads(connection.audit_logs[-1]["detail_json"]) == {"comment": "needs cleanup"}

    with pytest.raises(AdminReviewReportError, match="error.profileReview.notPending"):
        await approve_admin_profile_review(
            FakeEngine(connection),
            request_id=22,
            reviewer_id="user-admin",
            platform_roles=["USER_ADMIN"],
            http_request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 11, 2, tzinfo=UTC),
        )


@pytest.mark.anyio
async def test_admin_report_profile_mutations_enforce_roles_and_disposition() -> None:
    engine = FakeEngine(FakeMutationConnection())

    with pytest.raises(AdminReviewReportError, match="error.admin.skillReport.readDenied"):
        await resolve_admin_skill_report(
            engine,
            report_id=10,
            actor_user_id="user",
            platform_roles=["USER"],
            disposition=None,
            comment=None,
            request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )
    with pytest.raises(AdminReviewReportError, match="error.skill.lifecycle.noPermission"):
        await resolve_admin_skill_report(
            engine,
            report_id=10,
            actor_user_id="skill-admin",
            platform_roles=["SKILL_ADMIN"],
            disposition="RESOLVE_AND_HIDE",
            comment=None,
            request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )
    with pytest.raises(AdminReviewReportError, match="error.skill.report.disposition.invalid"):
        await resolve_admin_skill_report(
            engine,
            report_id=10,
            actor_user_id="skill-admin",
            platform_roles=["SUPER_ADMIN"],
            disposition="bad",
            comment=None,
            request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )
    with pytest.raises(AdminReviewReportError, match="error.profileReview.readDenied"):
        await reject_admin_profile_review(
            engine,
            request_id=21,
            reviewer_id="skill-admin",
            platform_roles=["SKILL_ADMIN"],
            comment="no",
            http_request_id=None,
            client_ip=None,
            user_agent=None,
            now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        )


def test_admin_review_report_mutation_routes_use_java_envelopes_and_roles() -> None:
    app = create_app()
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
    app.state.admin_skill_report_resolver = lambda report_id, payload, user, request_meta: {
        "id": report_id,
        "status": "RESOLVED",
    }
    app.state.admin_skill_report_dismisser = lambda report_id, payload, user, request_meta: {
        "id": report_id,
        "status": "DISMISSED",
    }
    app.state.admin_profile_review_approver = lambda request_id, user, request_meta: {
        "id": request_id,
        "status": "APPROVED",
    }
    app.state.admin_profile_review_rejecter = lambda request_id, payload, user, request_meta: {
        "id": request_id,
        "status": "REJECTED",
    }
    client = TestClient(app)

    assert client.post("/api/v1/admin/skill-reports/10/resolve", headers={"X-Mock-User-Id": "user"}).status_code == 403
    resolve_response = client.post(
        "/api/v1/admin/skill-reports/10/resolve",
        headers={"X-Mock-User-Id": "skill-admin", "X-Request-Id": "req-route"},
        json={"comment": "ok"},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert resolve_response.json()["data"] == {"id": 10, "status": "RESOLVED"}

    dismiss_response = client.post("/api/v1/admin/skill-reports/11/dismiss", headers={"X-Mock-User-Id": "super-admin"})
    assert dismiss_response.status_code == 200
    assert dismiss_response.json()["data"] == {"id": 11, "status": "DISMISSED"}

    assert client.post("/api/v1/admin/profile-reviews/20/approve", headers={"X-Mock-User-Id": "skill-admin"}).status_code == 403
    approve_response = client.post("/api/v1/admin/profile-reviews/20/approve", headers={"X-Mock-User-Id": "user-admin"})
    assert approve_response.status_code == 200
    assert approve_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert approve_response.json()["data"] == {"id": 20, "status": "APPROVED"}

    reject_response = client.post(
        "/api/v1/admin/profile-reviews/21/reject",
        headers={"X-Mock-User-Id": "super-admin"},
        json={"comment": "reject"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["data"] == {"id": 21, "status": "REJECTED"}
