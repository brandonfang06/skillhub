from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.skill import (
    SkillConfirmPublishInput,
    SkillLifecycleError,
    confirm_publish_skill_version,
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
    def __init__(self, connection: "FakeConfirmPublishConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeConfirmPublishConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeConfirmPublishConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeConfirmPublishConnection:
    def __init__(
        self,
        *,
        skill_visibility: str = "PRIVATE",
        version_status: str = "UPLOADED",
        owner_id: str = "owner",
        namespace_role: str | None = None,
    ) -> None:
        self.skill_visibility = skill_visibility
        self.version_status = version_status
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
                {
                    "skill_id": 101,
                    "namespace_id": 20,
                    "namespace_slug": "team-a",
                    "namespace_status": "ACTIVE",
                    "skill_slug": "agent-helper",
                    "owner_id": self.owner_id,
                    "visibility": self.skill_visibility,
                    "status": "ACTIVE",
                    "latest_version_id": None,
                }
            )
        if "FROM namespace_member" in sql:
            return FakeResult({"role": self.namespace_role}) if self.namespace_role else FakeResult()
        if "FROM skill_version" in sql:
            return FakeResult({"version_id": 42, "version": "1.1.0", "status": self.version_status})
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "UPDATE skill" in sql:
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def confirm_input(**overrides: Any) -> SkillConfirmPublishInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.1.0",
        "user_id": "owner",
        "request_id": "req-confirm-publish",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 14, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillConfirmPublishInput(**data)


@pytest.mark.anyio
async def test_confirm_publish_updates_private_uploaded_version_latest_pointer_and_audit() -> None:
    connection = FakeConfirmPublishConnection()

    response = await confirm_publish_skill_version(FakeEngine(connection), confirm_input())

    assert response == {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert version_update < skill_update < audit_insert
    assert "updated_at" not in connection.statements[version_update]
    assert connection.params[version_update]["status"] == "PUBLISHED"
    assert connection.params[version_update]["published_at"] == datetime(2026, 6, 9, 14, 30, tzinfo=UTC)
    assert connection.params[skill_update]["latest_version_id"] == 42
    assert connection.params[skill_update]["updated_by"] == "owner"
    assert connection.params[audit_insert]["action"] == "CONFIRM_PUBLISH"
    assert connection.params[audit_insert]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_insert]["target_id"] == 42
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"version": "1.1.0"}


@pytest.mark.anyio
async def test_confirm_publish_allows_namespace_manager_for_private_draft_version() -> None:
    connection = FakeConfirmPublishConnection(version_status="DRAFT", owner_id="owner", namespace_role="ADMIN")

    response = await confirm_publish_skill_version(FakeEngine(connection), confirm_input(user_id="manager"))

    assert response["status"] == "PUBLISHED"
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    assert connection.params[version_update]["status"] == "PUBLISHED"


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_private_skill() -> None:
    connection = FakeConfirmPublishConnection(skill_visibility="PUBLIC")

    with pytest.raises(SkillLifecycleError, match="error.skill.confirm.notPrivate"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_uploaded_or_draft_version() -> None:
    connection = FakeConfirmPublishConnection(version_status="PENDING_REVIEW")

    with pytest.raises(SkillLifecycleError, match="error.skill.version.confirm.notUploaded"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_manager_before_mutation() -> None:
    connection = FakeConfirmPublishConnection(owner_id="owner", namespace_role="MEMBER")

    with pytest.raises(SkillLifecycleError, match="error.skill.lifecycle.noPermission"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input(user_id="viewer"))

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


def test_confirm_publish_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[SkillConfirmPublishInput] = []

    async def confirmer(lifecycle_input: SkillConfirmPublishInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}

    app.state.skill_confirm_publish_writer = confirmer
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/confirm-publish",
        json={"version": "1.1.0"},
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "confirm-publish-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["requestId"] == "confirm-publish-test"
    assert body["data"]["action"] == "CONFIRM_PUBLISH"
    assert body["data"]["status"] == "PUBLISHED"
    assert seen[0].namespace == "team-a"
    assert seen[0].version == "1.1.0"
    assert seen[0].user_id == "owner"


def test_confirm_publish_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post(
        "/api/v1/skills/team-a/agent-helper/confirm-publish",
        json={"version": "1.1.0"},
    ).status_code == 401
