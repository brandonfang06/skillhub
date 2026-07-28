from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillVisibilityUpdateInput,
    update_skill_visibility,
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
    def __init__(self, connection: "FakeVisibilityConnection") -> None:
        self.connection = connection
        self.rolled_back = False

    async def __aenter__(self) -> "FakeVisibilityConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.rolled_back = exc_type is not None


class FakeEngine:
    def __init__(self, connection: "FakeVisibilityConnection") -> None:
        self.transaction = FakeTransaction(connection)

    def begin(self) -> FakeTransaction:
        return self.transaction


class FakeVisibilityConnection:
    def __init__(
        self,
        *,
        owner_id: str = "owner",
        namespace_role: str | None = None,
        namespace_status: str = "ACTIVE",
        visibility: str = "PRIVATE",
        fail_on_audit: bool = False,
        fail_on_search: bool = False,
    ) -> None:
        self.owner_id = owner_id
        self.namespace_role = namespace_role
        self.namespace_status = namespace_status
        self.visibility = visibility
        self.fail_on_audit = fail_on_audit
        self.fail_on_search = fail_on_search
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
                        "namespace_status": self.namespace_status,
                        "skill_slug": "agent-helper",
                        "owner_id": self.owner_id,
                        "visibility": self.visibility,
                        "status": "ACTIVE",
                        "latest_version_id": 501,
                    }
                ]
            )
        if "FROM namespace_member" in sql:
            return FakeResult([{"role": self.namespace_role}]) if self.namespace_role else FakeResult()
        if "UPDATE skill" in sql:
            self.visibility = str(values["visibility"])
            return FakeResult()
        if "INSERT INTO audit_log" in sql and self.fail_on_audit:
            raise RuntimeError("audit write failed")
        if "FROM skill s" in sql and "JOIN LATERAL" in sql:
            return FakeResult(
                [
                    {
                        "skill_id": 101,
                        "namespace_id": 20,
                        "namespace_slug": "team-a",
                        "owner_id": self.owner_id,
                        "slug": "agent-helper",
                        "display_name": "Agent Helper",
                        "summary": "Helps agents",
                        "visibility": self.visibility,
                        "status": "ACTIVE",
                        "parsed_metadata_json": json.dumps({"name": "Agent Helper"}),
                    }
                ]
            )
        if "FROM skill_label" in sql:
            return FakeResult()
        if "INSERT INTO skill_search_document" in sql and self.fail_on_search:
            raise RuntimeError("search document write failed")
        return FakeResult()


def visibility_input(**overrides: Any) -> SkillVisibilityUpdateInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "visibility": "NAMESPACE_ONLY",
        "user_id": "owner",
        "request_id": "visibility-test",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 7, 27, 10, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillVisibilityUpdateInput(**data)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("user_id", "owner_id", "namespace_role"),
    [
        ("owner", "owner", None),
        ("namespace-owner", "skill-owner", "OWNER"),
        ("namespace-admin", "skill-owner", "ADMIN"),
    ],
)
async def test_update_visibility_allows_skill_owner_and_namespace_managers(
    user_id: str,
    owner_id: str,
    namespace_role: str | None,
) -> None:
    connection = FakeVisibilityConnection(owner_id=owner_id, namespace_role=namespace_role)

    result = await update_skill_visibility(
        FakeEngine(connection),
        visibility_input(user_id=user_id),
    )

    assert result == {"skillId": 101, "visibility": "NAMESPACE_ONLY", "changed": True}
    skill_read = next(sql for sql in connection.statements if "FROM namespace n" in sql)
    assert "FOR UPDATE OF n, s" in skill_read
    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    search_index = next(
        index
        for index, sql in enumerate(connection.statements)
        if "INSERT INTO skill_search_document" in sql
    )
    assert update_index < audit_index < search_index
    assert connection.params[update_index]["visibility"] == "NAMESPACE_ONLY"
    assert connection.params[update_index]["updated_by"] == user_id
    assert "skill_version" not in connection.statements[update_index]
    assert "review_task" not in connection.statements[update_index]
    assert connection.params[audit_index]["actor_user_id"] == user_id
    assert connection.params[audit_index]["action"] == "UPDATE_SKILL_VISIBILITY"
    assert json.loads(connection.params[audit_index]["detail_json"]) == {
        "previousVisibility": "PRIVATE",
        "visibility": "NAMESPACE_ONLY",
    }
    assert connection.params[search_index]["visibility"] == "NAMESPACE_ONLY"


@pytest.mark.anyio
async def test_update_visibility_forbids_plain_namespace_member() -> None:
    connection = FakeVisibilityConnection(owner_id="skill-owner", namespace_role="MEMBER")

    with pytest.raises(SkillLifecycleError, match="error.skill.lifecycle.noPermission"):
        await update_skill_visibility(
            FakeEngine(connection),
            visibility_input(user_id="namespace-member"),
        )

    assert not any("UPDATE skill" in sql for sql in connection.statements)
    assert not any("INSERT INTO audit_log" in sql for sql in connection.statements)
    assert not any("skill_search_document" in sql for sql in connection.statements)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("namespace_status", "expected_error"),
    [
        ("FROZEN", "error.namespace.frozen"),
        ("ARCHIVED", "error.namespace.archived"),
    ],
)
async def test_update_visibility_rejects_inactive_namespace(
    namespace_status: str,
    expected_error: str,
) -> None:
    connection = FakeVisibilityConnection(namespace_status=namespace_status)

    with pytest.raises(SkillLifecycleError, match=expected_error):
        await update_skill_visibility(FakeEngine(connection), visibility_input())

    assert not any("UPDATE skill" in sql for sql in connection.statements)
    assert not any("INSERT INTO audit_log" in sql for sql in connection.statements)
    assert not any("skill_search_document" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_update_visibility_is_idempotent_when_value_is_unchanged() -> None:
    connection = FakeVisibilityConnection(visibility="NAMESPACE_ONLY")

    result = await update_skill_visibility(FakeEngine(connection), visibility_input())

    assert result == {"skillId": 101, "visibility": "NAMESPACE_ONLY", "changed": False}
    assert not any("UPDATE skill" in sql for sql in connection.statements)
    assert not any("INSERT INTO audit_log" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_update_visibility_rejects_invalid_internal_value() -> None:
    connection = FakeVisibilityConnection()

    with pytest.raises(SkillLifecycleError, match="error.skill.publish.visibility.invalid"):
        await update_skill_visibility(
            FakeEngine(connection),
            visibility_input(visibility="TEAM_ONLY"),
        )

    assert connection.statements == []


@pytest.mark.anyio
async def test_update_visibility_rolls_back_when_audit_write_fails() -> None:
    connection = FakeVisibilityConnection(fail_on_audit=True)
    engine = FakeEngine(connection)

    with pytest.raises(RuntimeError, match="audit write failed"):
        await update_skill_visibility(engine, visibility_input())

    assert any("UPDATE skill" in sql for sql in connection.statements)
    assert engine.transaction.rolled_back


@pytest.mark.anyio
async def test_update_visibility_rolls_back_when_search_sync_fails() -> None:
    connection = FakeVisibilityConnection(fail_on_search=True)
    engine = FakeEngine(connection)

    with pytest.raises(RuntimeError, match="search document write failed"):
        await update_skill_visibility(engine, visibility_input())

    assert any("UPDATE skill" in sql for sql in connection.statements)
    assert any("INSERT INTO audit_log" in sql for sql in connection.statements)
    assert engine.transaction.rolled_back


def test_visibility_routes_return_envelopes_for_v1_and_web_aliases() -> None:
    app = create_app()
    seen: list[SkillVisibilityUpdateInput] = []

    async def writer(update_input: SkillVisibilityUpdateInput) -> dict[str, object]:
        seen.append(update_input)
        return {"skillId": 101, "visibility": update_input.visibility, "changed": True}

    app.state.skill_visibility_writer = writer
    client = TestClient(app)

    for path in [
        "/api/v1/skills/team-a/agent-helper/visibility",
        "/api/web/skills/team-a/agent-helper/visibility",
    ]:
        response = client.patch(
            path,
            json={"visibility": "NAMESPACE_ONLY"},
            headers={"X-Mock-User-Id": "maintainer", "X-Request-Id": "visibility-route-test"},
        )

        assert response.status_code == 200
        assert response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
        assert response.json()["requestId"] == "visibility-route-test"
        assert response.json()["data"] == {
            "skillId": 101,
            "visibility": "NAMESPACE_ONLY",
            "changed": True,
        }

    assert [item.user_id for item in seen] == ["maintainer", "maintainer"]
    assert all(item.namespace == "team-a" for item in seen)
    assert all(item.slug == "agent-helper" for item in seen)


def test_visibility_routes_require_authentication() -> None:
    client = TestClient(create_app())

    response = client.patch(
        "/api/web/skills/team-a/agent-helper/visibility",
        json={"visibility": "PRIVATE"},
    )

    assert response.status_code == 401


def test_visibility_routes_reject_invalid_visibility() -> None:
    app = create_app()
    writer_called = False

    async def writer(update_input: SkillVisibilityUpdateInput) -> dict[str, object]:
        nonlocal writer_called
        writer_called = True
        return {}

    app.state.skill_visibility_writer = writer
    client = TestClient(app)

    response = client.patch(
        "/api/v1/skills/team-a/agent-helper/visibility",
        json={"visibility": "TEAM_ONLY"},
        headers={"X-Mock-User-Id": "maintainer"},
    )

    assert response.status_code == 422
    assert not writer_called


def test_visibility_routes_map_workflow_permission_error() -> None:
    app = create_app()

    async def writer(update_input: SkillVisibilityUpdateInput) -> dict[str, object]:
        raise SkillLifecycleError("error.skill.lifecycle.noPermission", status_code=403)

    app.state.skill_visibility_writer = writer
    client = TestClient(app)

    response = client.patch(
        "/api/web/skills/team-a/agent-helper/visibility",
        json={"visibility": "PUBLIC"},
        headers={"X-Mock-User-Id": "namespace-member"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.skill.lifecycle.noPermission"
