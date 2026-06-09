from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.skill import (
    SkillArchiveInput,
    SkillLifecycleError,
    archive_skill,
    unarchive_skill,
)
from app.main import create_app


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeTransaction:
    async def __aenter__(self) -> "FakeSkillLifecycleConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def __init__(self, connection: "FakeSkillLifecycleConnection") -> None:
        self.connection = connection


class FakeEngine:
    def __init__(self, connection: "FakeSkillLifecycleConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeSkillLifecycleConnection:
    def __init__(
        self,
        *,
        skill_status: str = "ACTIVE",
        owner_id: str = "owner",
        namespace_role: str | None = "ADMIN",
    ) -> None:
        self.skill_status = skill_status
        self.owner_id = owner_id
        self.namespace_role = namespace_role
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM namespace n" in sql and "JOIN skill s" in sql:
            return FakeResult(
                [
                    {
                        "skill_id": 101,
                        "namespace_id": 20,
                        "namespace_slug": "team-a",
                        "namespace_status": "ACTIVE",
                        "skill_slug": "agent-helper",
                        "owner_id": self.owner_id,
                        "status": self.skill_status,
                    }
                ]
            )
        if "FROM namespace_member" in sql:
            return FakeResult([{"role": self.namespace_role}]) if self.namespace_role else FakeResult()
        return FakeResult()


def archive_input(**overrides: Any) -> SkillArchiveInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "user_id": "maintainer",
        "reason": "cleanup",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 9, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillArchiveInput(**data)


@pytest.mark.anyio
async def test_archive_skill_updates_status_and_writes_audit_reason() -> None:
    connection = FakeSkillLifecycleConnection(namespace_role="ADMIN")

    response = await archive_skill(FakeEngine(connection), archive_input())

    assert response == {"skillId": 101, "versionId": None, "action": "ARCHIVE", "status": "ARCHIVED"}
    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert update_index < audit_index
    assert connection.params[update_index]["status"] == "ARCHIVED"
    assert connection.params[update_index]["updated_by"] == "maintainer"
    assert connection.params[audit_index]["actor_user_id"] == "maintainer"
    assert connection.params[audit_index]["action"] == "ARCHIVE_SKILL"
    assert connection.params[audit_index]["target_type"] == "SKILL"
    assert connection.params[audit_index]["target_id"] == 101
    assert json.loads(connection.params[audit_index]["detail_json"]) == {"reason": "cleanup"}


@pytest.mark.anyio
async def test_unarchive_skill_updates_status_and_writes_null_audit_detail() -> None:
    connection = FakeSkillLifecycleConnection(skill_status="ARCHIVED", owner_id="owner", namespace_role=None)

    response = await unarchive_skill(FakeEngine(connection), archive_input(user_id="owner", reason=None))

    assert response == {"skillId": 101, "versionId": None, "action": "UNARCHIVE", "status": "ACTIVE"}
    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert update_index < audit_index
    assert connection.params[update_index]["status"] == "ACTIVE"
    assert connection.params[audit_index]["action"] == "UNARCHIVE_SKILL"
    assert connection.params[audit_index]["detail_json"] is None


@pytest.mark.anyio
async def test_archive_skill_forbids_non_owner_without_namespace_admin_role() -> None:
    connection = FakeSkillLifecycleConnection(owner_id="owner", namespace_role="MEMBER")

    with pytest.raises(SkillLifecycleError, match="error.skill.lifecycle.noPermission"):
        await archive_skill(FakeEngine(connection), archive_input(user_id="viewer"))

    assert not any("UPDATE skill" in sql for sql in connection.statements)
    assert not any("INSERT INTO audit_log" in sql for sql in connection.statements)


def test_skill_lifecycle_archive_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[SkillArchiveInput] = []

    async def archiver(lifecycle_input: SkillArchiveInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": None, "action": "ARCHIVE", "status": "ARCHIVED"}

    async def unarchiver(lifecycle_input: SkillArchiveInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": None, "action": "UNARCHIVE", "status": "ACTIVE"}

    app.state.skill_archive_writer = archiver
    app.state.skill_unarchive_writer = unarchiver
    client = TestClient(app)

    archived = client.post(
        "/api/v1/skills/team-a/agent-helper/archive",
        json={"reason": "cleanup"},
        headers={"X-Mock-User-Id": "maintainer", "X-Request-Id": "archive-test"},
    )
    unarchived = client.post(
        "/api/web/skills/team-a/agent-helper/unarchive",
        headers={"X-Mock-User-Id": "maintainer", "X-Request-Id": "unarchive-test"},
    )

    assert archived.status_code == 200
    assert archived.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert archived.json()["requestId"] == "archive-test"
    assert archived.json()["data"]["action"] == "ARCHIVE"
    assert unarchived.status_code == 200
    assert unarchived.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert unarchived.json()["requestId"] == "unarchive-test"
    assert unarchived.json()["data"]["status"] == "ACTIVE"
    assert seen[0].namespace == "team-a"
    assert seen[0].slug == "agent-helper"
    assert seen[0].reason == "cleanup"
    assert seen[1].reason is None


def test_skill_lifecycle_archive_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post("/api/v1/skills/team-a/agent-helper/archive").status_code == 401
    assert client.post("/api/web/skills/team-a/agent-helper/unarchive").status_code == 401
