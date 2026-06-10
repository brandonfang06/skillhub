from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.reports.skill_reports import SkillReportSubmitError, submit_skill_report


class FakeScalarResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value


class FakeMappings:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return self.rows
        return [] if self.row is None else [self.row]


class FakeResult:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        scalar: Any = None,
    ) -> None:
        self.row = row
        self.rows = rows
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.row, self.rows)

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeBegin:
    def __init__(self, connection: "FakeSkillReportConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSkillReportConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSkillReportConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)


class FakeSkillReportConnection:
    def __init__(self) -> None:
        self.skill = {
            "id": 100,
            "namespace_id": 10,
            "slug": "reported-skill",
            "display_name": "Reported Skill",
            "owner_id": "owner-1",
            "status": "ACTIVE",
            "hidden": False,
            "namespace_slug": "team-ai",
        }
        self.pending_duplicate = False
        self.report_id = 901
        self.report: dict[str, Any] | None = None
        self.audits: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        values = params or {}
        self.statements.append(sql)
        if "FROM namespace n" in sql and "JOIN skill s" in sql:
            expected_namespace = str(values["namespace_slug"])
            return FakeResult(row=self.skill.copy() if expected_namespace == "team-ai" else None)
        if "FROM skill_report" in sql and "status = 'PENDING'" in sql:
            return FakeResult(scalar=1 if self.pending_duplicate else 0)
        if sql.startswith("INSERT INTO skill_report"):
            self.report = {
                "id": self.report_id,
                "skill_id": values["skill_id"],
                "namespace_id": values["namespace_id"],
                "reporter_id": values["reporter_id"],
                "reason": values["reason"],
                "details": values["details"],
                "status": "PENDING",
                "created_at": values["created_at"],
            }
            return FakeResult(scalar=self.report_id)
        if sql.startswith("INSERT INTO audit_log"):
            self.audits.append(dict(values))
            return FakeResult()
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"user_id": "skill-admin"}, {"user_id": "super-admin"}])
        if sql.startswith("INSERT INTO notification"):
            self.notifications.append(dict(values))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def auth_user(user_id: str = "reporter-1") -> dict[str, Any]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_submit_skill_report_inserts_report_audit_and_platform_notifications() -> None:
    connection = FakeSkillReportConnection()
    result = run(
        submit_skill_report(
            FakeEngine(connection),
            namespace_slug="@team-ai",
            skill_slug="reported-skill",
            reporter_id="reporter-1",
            reason="  policy violation  ",
            details="  suspicious prompt  ",
            request_id="req-report",
            client_ip="127.0.0.1",
            user_agent="pytest",
            now=datetime(2026, 6, 11, 8, 0, tzinfo=UTC),
        )
    )

    assert result == {"reportId": 901, "status": "PENDING"}
    assert connection.report is not None
    assert connection.report["reason"] == "policy violation"
    assert connection.report["details"] == "suspicious prompt"
    assert connection.audits == [
        {
            "actor_user_id": "reporter-1",
            "action": "REPORT_SKILL",
            "target_type": "SKILL",
            "target_id": 100,
            "request_id": "req-report",
            "client_ip": "127.0.0.1",
            "user_agent": "pytest",
            "detail_json": '{"reportId":901}',
            "created_at": datetime(2026, 6, 11, 8, 0, tzinfo=UTC),
        }
    ]
    assert [row["recipient_id"] for row in connection.notifications] == ["skill-admin", "super-admin"]
    assert connection.notifications[0]["recipient_id"] == "skill-admin"
    assert connection.notifications[0]["category"] == "REPORT"
    assert connection.notifications[0]["entity_type"] == "REPORT"
    assert connection.notifications[0]["event_type"] == "REPORT_SUBMITTED"
    assert connection.notifications[0]["entity_id"] == 901
    assert connection.notifications[0]["title"] == "Skill reported: Reported Skill"
    assert connection.notifications[0]["body_json"] == (
        '{"skillId":100,"skillName":"Reported Skill","slug":"reported-skill",'
        '"namespace":"team-ai","reportId":901,"reporterId":"reporter-1"}'
    )


def test_submit_skill_report_rejects_java_error_cases() -> None:
    connection = FakeSkillReportConnection()

    with pytest.raises(SkillReportSubmitError, match="error.skill.report.reason.required"):
        run(
            submit_skill_report(
                FakeEngine(connection),
                namespace_slug="team-ai",
                skill_slug="reported-skill",
                reporter_id="reporter-1",
                reason=" ",
                details=None,
                request_id=None,
                client_ip=None,
                user_agent=None,
            )
        )

    connection.skill["owner_id"] = "reporter-1"
    with pytest.raises(SkillReportSubmitError, match="error.skill.report.self"):
        run(
            submit_skill_report(
                FakeEngine(connection),
                namespace_slug="team-ai",
                skill_slug="reported-skill",
                reporter_id="reporter-1",
                reason="spam",
                details=None,
                request_id=None,
                client_ip=None,
                user_agent=None,
            )
        )

    connection.skill["owner_id"] = "owner-1"
    connection.pending_duplicate = True
    with pytest.raises(SkillReportSubmitError, match="error.skill.report.duplicate"):
        run(
            submit_skill_report(
                FakeEngine(connection),
                namespace_slug="team-ai",
                skill_slug="reported-skill",
                reporter_id="reporter-1",
                reason="spam",
                details=None,
                request_id=None,
                client_ip=None,
                user_agent=None,
            )
        )

    connection.pending_duplicate = False
    connection.skill["hidden"] = True
    with pytest.raises(SkillReportSubmitError, match="error.skill.report.unavailable"):
        run(
            submit_skill_report(
                FakeEngine(connection),
                namespace_slug="team-ai",
                skill_slug="reported-skill",
                reporter_id="reporter-1",
                reason="spam",
                details=None,
                request_id=None,
                client_ip=None,
                user_agent=None,
            )
        )


def test_skill_report_submit_routes_use_java_envelope_and_auth_bridge() -> None:
    app = create_app()
    captured: list[dict[str, Any]] = []
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.skill_report_submitter = lambda namespace, slug, payload, user, meta: captured.append(
        {
            "namespace": namespace,
            "slug": slug,
            "payload": payload,
            "user": user,
            "meta": meta,
        }
    ) or {"reportId": 77, "status": "PENDING"}
    client = TestClient(app)

    assert client.post("/api/v1/skills/team-ai/reported-skill/reports").status_code == 401

    response = client.post(
        "/api/v1/skills/@team-ai/reported-skill/reports",
        headers={"X-Mock-User-Id": "reporter-1", "X-Request-Id": "req-route"},
        json={"reason": "spam", "details": "bad"},
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "\u521b\u5efa\u6210\u529f"
    assert response.json()["data"] == {"reportId": 77, "status": "PENDING"}
    assert captured[0]["namespace"] == "@team-ai"
    assert captured[0]["slug"] == "reported-skill"
    assert captured[0]["payload"] == {"reason": "spam", "details": "bad"}
    assert captured[0]["user"]["userId"] == "reporter-1"
    assert captured[0]["meta"]["request_id"] == "req-route"

    web_response = client.post(
        "/api/web/skills/team-ai/reported-skill/reports",
        headers={"X-Mock-User-Id": "reporter-1"},
        json={"reason": "spam"},
    )
    assert web_response.status_code == 200
    assert web_response.json()["data"] == {"reportId": 77, "status": "PENDING"}
