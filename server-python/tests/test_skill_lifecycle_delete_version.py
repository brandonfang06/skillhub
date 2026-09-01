from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle import skill as skill_lifecycle
from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillVersionDeleteInput,
    delete_skill_version,
)
from app.main import create_app


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self.rows = rows or []
        self.row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        if self.row is not None:
            return self.row
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeTransaction:
    def __init__(self, connection: "FakeDeleteVersionConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeDeleteVersionConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeDeleteVersionConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeDeleteVersionConnection:
    def __init__(
        self,
        *,
        version_status: str = "UPLOADED",
        version_count: int = 2,
        latest_version_id: int | None = None,
        namespace_role: str | None = "ADMIN",
        owner_id: str = "owner",
        review_task_statuses: tuple[str, ...] = ("REJECTED",),
    ) -> None:
        self.version_status = version_status
        self.version_count = version_count
        self.latest_version_id = latest_version_id
        self.namespace_role = namespace_role
        self.owner_id = owner_id
        self.review_task_statuses = review_task_statuses
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM namespace n" in sql and "JOIN skill s" in sql:
            return FakeResult(
                row={
                    "skill_id": 101,
                    "namespace_id": 20,
                    "namespace_slug": "team-a",
                    "namespace_status": "ACTIVE",
                    "skill_slug": "agent-helper",
                    "owner_id": self.owner_id,
                    "status": "ACTIVE",
                    "latest_version_id": self.latest_version_id,
                }
            )
        if "FROM namespace_member" in sql:
            return FakeResult(row={"role": self.namespace_role}) if self.namespace_role else FakeResult()
        if "SELECT id" in sql and "status = 'PUBLISHED'" in sql:
            return FakeResult(row={"id": 41})
        if "FROM skill_version" in sql and "FOR UPDATE" in sql:
            rows = [
                {"version_id": 42, "version": "1.1.0", "status": self.version_status},
                *[
                    {"version_id": 43 + index, "version": f"1.{2 + index}.0", "status": "UPLOADED"}
                    for index in range(max(self.version_count - 1, 0))
                ],
            ]
            return FakeResult(rows=rows)
        if "FROM review_task" in sql and "FOR UPDATE" in sql:
            return FakeResult(
                rows=[
                    {"review_task_id": 91 + index, "status": status}
                    for index, status in enumerate(self.review_task_statuses)
                ]
            )
        if "SELECT storage_key" in sql:
            return FakeResult(
                rows=[
                    {"storage_key": "skills/101/42/SKILL.md"},
                    {"storage_key": ""},
                    {"storage_key": None},
                    {"storage_key": "skills/101/42/main.py"},
                ]
            )
        return FakeResult()


def delete_input(**overrides: Any) -> SkillVersionDeleteInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.1.0",
        "user_id": "maintainer",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillVersionDeleteInput(**data)


@pytest.mark.anyio
async def test_delete_skill_version_deletes_metadata_audit_and_returns_storage_keys() -> None:
    connection = FakeDeleteVersionConnection()

    result = await delete_skill_version(FakeEngine(connection), delete_input())

    assert result.response == {"skillId": 101, "versionId": 42, "action": "DELETE_VERSION", "status": "1.1.0"}
    assert result.storage_keys == [
        "skills/101/42/SKILL.md",
        "skills/101/42/main.py",
        "packages/101/42/bundle.zip",
    ]
    assert any("DELETE FROM skill_file" in statement for statement in connection.statements)
    outbox_delete_index = next(
        index
        for index, sql in enumerate(connection.statements)
        if "DELETE FROM scan_task_outbox" in sql
    )
    assert connection.params[outbox_delete_index] == {"version_id": 42}
    lock_index = next(index for index, sql in enumerate(connection.statements) if "FROM skill_version" in sql)
    assert "ORDER BY id" in connection.statements[lock_index]
    assert "FOR UPDATE" in connection.statements[lock_index]
    review_delete_index = next(index for index, sql in enumerate(connection.statements) if "DELETE FROM review_task" in sql)
    assert any("UPDATE security_audit" in statement and "deleted_at" in statement for statement in connection.statements)
    version_delete_index = next(index for index, sql in enumerate(connection.statements) if "DELETE FROM skill_version" in sql)
    assert outbox_delete_index < version_delete_index
    assert review_delete_index < version_delete_index
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert connection.params[audit_index]["action"] == "DELETE_SKILL_VERSION"
    assert connection.params[audit_index]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_index]["target_id"] == 42
    assert json.loads(connection.params[audit_index]["detail_json"]) == {"version": "1.1.0"}


@pytest.mark.anyio
async def test_delete_skill_version_recalculates_latest_when_deleting_latest_pointer() -> None:
    connection = FakeDeleteVersionConnection(latest_version_id=42)

    await delete_skill_version(FakeEngine(connection), delete_input())

    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    assert "latest_version_id = :latest_version_id" in connection.statements[update_index]
    assert connection.params[update_index]["latest_version_id"] == 41
    assert connection.params[update_index]["updated_by"] == "maintainer"


@pytest.mark.anyio
async def test_delete_skill_version_rejects_published_version() -> None:
    connection = FakeDeleteVersionConnection(version_status="PUBLISHED")

    with pytest.raises(SkillLifecycleError, match="error.skill.version.delete.unsupported"):
        await delete_skill_version(FakeEngine(connection), delete_input())

    assert not any("DELETE FROM skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_delete_skill_version_rejects_last_version() -> None:
    connection = FakeDeleteVersionConnection(version_count=1)

    with pytest.raises(SkillLifecycleError, match="error.skill.version.delete.lastVersion"):
        await delete_skill_version(FakeEngine(connection), delete_input())

    assert not any("DELETE FROM skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_delete_skill_version_rejects_inconsistent_pending_review() -> None:
    connection = FakeDeleteVersionConnection(review_task_statuses=("PENDING",))

    with pytest.raises(SkillLifecycleError, match="error.skill.version.delete.pendingReview") as exc_info:
        await delete_skill_version(FakeEngine(connection), delete_input())

    assert exc_info.value.status_code == 409
    assert not any("DELETE FROM review_task" in statement for statement in connection.statements)
    assert not any("DELETE FROM skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_delete_rejected_version_archives_review_before_deleting_task(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeDeleteVersionConnection(version_status="REJECTED")
    archived_requests: list[object] = []

    async def read_attempt(_connection: object, _version: object) -> object:
        return SimpleNamespace(original_skill_version_id=42)

    async def archive_attempt(_connection: object, request: object) -> None:
        archived_requests.append(request)

    monkeypatch.setattr(skill_lifecycle, "read_rejected_review_attempt", read_attempt)
    monkeypatch.setattr(skill_lifecycle, "archive_review_attempt", archive_attempt)

    await delete_skill_version(FakeEngine(connection), delete_input())

    assert len(archived_requests) == 1
    archive_request = archived_requests[0]
    assert archive_request.replacement_version_id is None
    assert archive_request.replacement_review_task_id is None
    assert archive_request.archive_reason == "REJECTED_VERSION_DELETE"
    archive_index = next(index for index, sql in enumerate(connection.statements) if "DELETE FROM review_task" in sql)
    assert archive_index > 0


@pytest.mark.anyio
async def test_delete_rejected_version_without_review_history_preserves_legacy_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeDeleteVersionConnection(version_status="REJECTED", review_task_statuses=())

    async def unexpected_read(_connection: object, _version: object) -> object:
        raise AssertionError("missing review history must not be archived")

    monkeypatch.setattr(skill_lifecycle, "read_rejected_review_attempt", unexpected_read)

    result = await delete_skill_version(FakeEngine(connection), delete_input())

    assert result.response["versionId"] == 42
    assert any("DELETE FROM skill_version" in statement for statement in connection.statements)


def test_delete_skill_version_routes_return_java_envelopes_and_delete_storage(tmp_path) -> None:
    app = create_app()
    seen: list[SkillVersionDeleteInput] = []
    deleted: list[str] = []

    async def deleter(delete_version_input: SkillVersionDeleteInput):
        seen.append(delete_version_input)
        return SimpleNamespace(
            response={"skillId": 101, "versionId": 42, "action": "DELETE_VERSION", "status": "1.1.0"},
            storage_keys=["skills/101/42/SKILL.md"],
            namespace="team-a",
            slug="agent-helper",
            skill_id=101,
        )

    async def storage_deleter(engine: object, storage_base_path: str, result: object):
        deleted.extend(result.storage_keys)
        assert storage_base_path == str(tmp_path)

    app.state.skill_delete_version_writer = deleter
    app.state.skill_delete_storage_cleanup = storage_deleter
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path=str(tmp_path))
    client = TestClient(app)

    response = client.delete(
        "/api/web/skills/team-a/agent-helper/versions/1.1.0",
        headers={"X-Mock-User-Id": "maintainer", "X-Request-Id": "delete-version-test"},
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert response.json()["requestId"] == "delete-version-test"
    assert response.json()["data"]["action"] == "DELETE_VERSION"
    assert seen[0].namespace == "team-a"
    assert seen[0].version == "1.1.0"
    assert deleted == ["skills/101/42/SKILL.md"]


def test_delete_skill_version_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.delete("/api/v1/skills/team-a/agent-helper/versions/1.1.0").status_code == 401
