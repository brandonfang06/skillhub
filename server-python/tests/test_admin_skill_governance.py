from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.skill import (
    AdminSkillGovernanceError,
    AdminSkillGovernanceInput,
    hide_skill_as_admin,
    unhide_skill_as_admin,
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
    def __init__(self, connection: "FakeAdminSkillConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeAdminSkillConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeAdminSkillConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeAdminSkillConnection:
    def __init__(self, *, skill_status: str = "ACTIVE", missing_skill: bool = False) -> None:
        self.skill_status = skill_status
        self.missing_skill = missing_skill
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM skill" in sql and "WHERE id = :skill_id" in sql:
            if self.missing_skill:
                return FakeResult()
            return FakeResult({"skill_id": 10, "status": self.skill_status})
        if "UPDATE skill" in sql:
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def admin_input(**overrides: Any) -> AdminSkillGovernanceInput:
    data: dict[str, Any] = {
        "skill_id": 10,
        "actor_user_id": "admin",
        "reason": "policy",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "request_id": "req-admin-hide",
        "now": datetime(2026, 6, 9, 17, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return AdminSkillGovernanceInput(**data)


@pytest.mark.anyio
async def test_hide_skill_as_admin_sets_hidden_overlay_and_audits_reason() -> None:
    connection = FakeAdminSkillConnection()

    response = await hide_skill_as_admin(FakeEngine(connection), admin_input())

    assert response == {"skillId": 10, "versionId": None, "action": "HIDE", "status": "ACTIVE"}
    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert update_index < audit_index
    assert connection.params[update_index]["hidden"] is True
    assert connection.params[update_index]["hidden_by"] == "admin"
    assert connection.params[update_index]["hidden_at"] == datetime(2026, 6, 9, 17, 30, tzinfo=UTC)
    assert connection.params[update_index]["updated_by"] == "admin"
    assert connection.params[audit_index]["action"] == "HIDE_SKILL"
    assert connection.params[audit_index]["target_type"] == "SKILL"
    assert connection.params[audit_index]["target_id"] == 10
    assert json.loads(connection.params[audit_index]["detail_json"]) == {"reason": "policy"}


@pytest.mark.anyio
async def test_unhide_skill_as_admin_clears_hidden_overlay_and_audits_null_detail() -> None:
    connection = FakeAdminSkillConnection(skill_status="ARCHIVED")

    response = await unhide_skill_as_admin(FakeEngine(connection), admin_input(reason=None))

    assert response == {"skillId": 10, "versionId": None, "action": "UNHIDE", "status": "ARCHIVED"}
    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert connection.params[update_index]["hidden"] is False
    assert connection.params[update_index]["hidden_by"] is None
    assert connection.params[update_index]["hidden_at"] is None
    assert connection.params[audit_index]["action"] == "UNHIDE_SKILL"
    assert connection.params[audit_index]["detail_json"] is None


@pytest.mark.anyio
async def test_admin_skill_governance_raises_not_found_before_mutation() -> None:
    connection = FakeAdminSkillConnection(missing_skill=True)

    with pytest.raises(AdminSkillGovernanceError, match="error.skill.notFound") as exc_info:
        await hide_skill_as_admin(FakeEngine(connection), admin_input())

    assert exc_info.value.status_code == 404
    assert not any("UPDATE skill" in sql for sql in connection.statements)


def auth_user(roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": "admin",
        "displayName": "Admin",
        "email": "admin@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["SUPER_ADMIN"],
    }


def test_admin_hide_unhide_routes_require_super_admin_and_return_java_envelopes() -> None:
    app = create_app()
    seen: list[AdminSkillGovernanceInput] = []
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])

    async def hider(governance_input: AdminSkillGovernanceInput) -> dict[str, object]:
        seen.append(governance_input)
        return {"skillId": governance_input.skill_id, "versionId": None, "action": "HIDE", "status": "ACTIVE"}

    async def unhider(governance_input: AdminSkillGovernanceInput) -> dict[str, object]:
        seen.append(governance_input)
        return {"skillId": governance_input.skill_id, "versionId": None, "action": "UNHIDE", "status": "ACTIVE"}

    app.state.admin_skill_hide_writer = hider
    app.state.admin_skill_unhide_writer = unhider
    client = TestClient(app)

    hide_response = client.post(
        "/api/v1/admin/skills/10/hide",
        json={"reason": "policy"},
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "admin-hide-test"},
    )
    unhide_response = client.post(
        "/api/v1/admin/skills/10/unhide",
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "admin-unhide-test"},
    )

    assert hide_response.status_code == 200
    assert hide_response.json()["code"] == 0
    assert hide_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert hide_response.json()["requestId"] == "admin-hide-test"
    assert hide_response.json()["data"] == {"skillId": 10, "versionId": None, "action": "HIDE", "status": "ACTIVE"}
    assert unhide_response.status_code == 200
    assert unhide_response.json()["data"]["action"] == "UNHIDE"
    assert seen[0].reason == "policy"
    assert seen[1].reason is None


def test_admin_hide_unhide_routes_reject_missing_or_non_super_admin_user() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SKILL_ADMIN"])
    client = TestClient(app)

    assert client.post("/api/v1/admin/skills/10/hide", json={"reason": "policy"}).status_code == 401
    assert client.post(
        "/api/v1/admin/skills/10/hide",
        json={"reason": "policy"},
        headers={"X-Mock-User-Id": "skill-admin"},
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/skills/10/unhide",
        headers={"X-Mock-User-Id": "skill-admin"},
    ).status_code == 403
