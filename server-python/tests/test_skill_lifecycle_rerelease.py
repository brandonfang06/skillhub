from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle import skill as lifecycle_skill_module
from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillRereleaseInput,
    rerelease_skill_version,
)
from app.main import create_app
from app.api import lifecycle as lifecycle_api
from app.publish.orchestration import PublishWriteInput, PublishWriteResult
from app.publish.side_effects import PublishSideEffectResult
from app.publish.storage import StoredPackageResult


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeTransaction:
    def __init__(self, connection: "FakeRereleaseConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeRereleaseConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeRereleaseConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeRereleaseConnection:
    def __init__(
        self,
        *,
        source_status: str = "PUBLISHED",
        target_exists: bool = False,
        owner_id: str = "owner",
        namespace_role: str | None = None,
        visibility: str = "PUBLIC",
        include_warning_file: bool = False,
    ) -> None:
        self.source_status = source_status
        self.target_exists = target_exists
        self.owner_id = owner_id
        self.namespace_role = namespace_role
        self.visibility = visibility
        self.include_warning_file = include_warning_file
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
                    "visibility": self.visibility,
                    "status": "ACTIVE",
                    "latest_version_id": 42,
                    "display_name": "Agent Helper",
                    "summary": "Source summary",
                }
            )
        if "FROM namespace_member" in sql:
            return FakeResult({"role": self.namespace_role}) if self.namespace_role else FakeResult()
        if "FROM skill_version" in sql and "version = :version" in sql:
            if values.get("version") == "2.0.0" and self.target_exists:
                return FakeResult({"version_id": 99, "version": "2.0.0", "status": "UPLOADED"})
            if values.get("version") == "2.0.0":
                return FakeResult()
            return FakeResult({"version_id": 42, "version": "1.0.0", "status": self.source_status})
        if "FROM skill_file" in sql:
            rows = [
                {
                    "file_path": "SKILL.md",
                    "content_type": "text/markdown",
                    "storage_key": "skills/101/42/SKILL.md",
                },
                {
                    "file_path": "src/main.py",
                    "content_type": "text/x-python",
                    "storage_key": "skills/101/42/src/main.py",
                },
            ]
            if self.include_warning_file:
                rows.append(
                    {
                        "file_path": "tools/demo.exe",
                        "content_type": "application/octet-stream",
                        "storage_key": "skills/101/42/tools/demo.exe",
                    }
                )
            return FakeResult(
                rows=rows
            )
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def rerelease_input(storage_base_path: str, **overrides: Any) -> SkillRereleaseInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.0.0",
        "target_version": " 2.0.0 ",
        "confirm_warnings": False,
        "user_id": "owner",
        "storage_base_path": storage_base_path,
        "request_id": "req-rerelease",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 16, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillRereleaseInput(**data)


def seed_source_files(base: Path) -> None:
    skill_md = base / "skills" / "101" / "42" / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_bytes(
        b"---\nname: Agent Helper\ndescription: Source summary\nversion: 1.0.0\n---\n# Agent Helper\n"
    )
    src = base / "skills" / "101" / "42" / "src" / "main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"print('ok')\n")
    warning_file = base / "skills" / "101" / "42" / "tools" / "demo.exe"
    warning_file.parent.mkdir(parents=True, exist_ok=True)
    warning_file.write_bytes(b"MZ")


def fake_publish_result(version_status: str) -> PublishWriteResult:
    return PublishWriteResult(
        skill_id=101,
        version_id=77,
        version_status=version_status,
        latest_version_updated=False,
        stored_package=StoredPackageResult([], "packages/101/77/bundle.zip", 0, 0, 0, True, True),
        side_effects=PublishSideEffectResult(None, None, None, []),
        replacement_deleted_keys=[],
        replacement_compensation_recorded=False,
    )


@pytest.mark.anyio
async def test_rerelease_rebuilds_entries_delegates_publish_and_audits(tmp_path: Path) -> None:
    seed_source_files(tmp_path)
    connection = FakeRereleaseConnection()
    seen: list[PublishWriteInput] = []

    async def publisher(write_input: PublishWriteInput) -> PublishWriteResult:
        seen.append(write_input)
        return fake_publish_result("PENDING_REVIEW")

    response = await rerelease_skill_version(FakeEngine(connection), rerelease_input(str(tmp_path)), publish_writer=publisher)

    assert response == {"skillId": 101, "versionId": 77, "action": "RERELEASE_VERSION", "status": "PENDING_REVIEW"}
    assert seen[0].namespace_id == 20
    assert seen[0].namespace_slug == "team-a"
    assert seen[0].slug == "agent-helper"
    assert seen[0].visibility == "PUBLIC"
    assert seen[0].version == "2.0.0"
    assert seen[0].auto_publish is False
    assert [entry.path for entry in seen[0].entries] == ["SKILL.md", "src/main.py"]
    assert b"version: 2.0.0" in seen[0].entries[0].content
    audit_index = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert connection.params[audit_index]["action"] == "RERELEASE_SKILL_VERSION"
    assert connection.params[audit_index]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_index]["target_id"] == 42
    assert json.loads(connection.params[audit_index]["detail_json"]) == {
        "sourceVersion": "1.0.0",
        "targetVersion": "2.0.0",
    }


@pytest.mark.anyio
async def test_rerelease_rebuilds_entries_from_object_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_object_storage_factory,
) -> None:
    storage = fake_object_storage_factory(
        {
            "skills/101/42/SKILL.md": (
                b"---\nname: Agent Helper\ndescription: Source summary\nversion: 1.0.0\n---\n# Agent Helper\n"
            ),
            "skills/101/42/src/main.py": b"print('object storage')\n",
        }
    )
    monkeypatch.setattr(lifecycle_skill_module, "object_storage_for_base_path", lambda storage_base_path: storage)
    connection = FakeRereleaseConnection()
    seen: list[PublishWriteInput] = []

    async def publisher(write_input: PublishWriteInput) -> PublishWriteResult:
        seen.append(write_input)
        return fake_publish_result("PENDING_REVIEW")

    response = await rerelease_skill_version(
        FakeEngine(connection),
        rerelease_input(str(tmp_path / "missing-local-storage")),
        publish_writer=publisher,
    )

    assert response["status"] == "PENDING_REVIEW"
    assert [entry.path for entry in seen[0].entries] == ["SKILL.md", "src/main.py"]
    assert b"version: 2.0.0" in seen[0].entries[0].content
    assert seen[0].entries[1].content == b"print('object storage')\n"
    assert not (tmp_path / "missing-local-storage").exists()


@pytest.mark.anyio
async def test_rerelease_private_skill_uses_uploaded_publish_status(tmp_path: Path) -> None:
    seed_source_files(tmp_path)
    connection = FakeRereleaseConnection(visibility="PRIVATE")
    seen: list[PublishWriteInput] = []

    async def publisher(write_input: PublishWriteInput) -> PublishWriteResult:
        seen.append(write_input)
        return fake_publish_result("UPLOADED")

    response = await rerelease_skill_version(FakeEngine(connection), rerelease_input(str(tmp_path)), publish_writer=publisher)

    assert response["status"] == "UPLOADED"
    assert seen[0].visibility == "PRIVATE"


@pytest.mark.anyio
async def test_rerelease_rejects_non_published_source_before_publish(tmp_path: Path) -> None:
    seed_source_files(tmp_path)
    connection = FakeRereleaseConnection(source_status="UPLOADED")

    with pytest.raises(SkillLifecycleError, match="error.skill.version.notPublished"):
        await rerelease_skill_version(FakeEngine(connection), rerelease_input(str(tmp_path)))


@pytest.mark.anyio
async def test_rerelease_rejects_duplicate_target_version_before_publish(tmp_path: Path) -> None:
    seed_source_files(tmp_path)
    connection = FakeRereleaseConnection(target_exists=True)

    with pytest.raises(SkillLifecycleError, match="error.skill.version.exists"):
        await rerelease_skill_version(FakeEngine(connection), rerelease_input(str(tmp_path)))


@pytest.mark.anyio
async def test_rerelease_requires_confirm_warnings_before_publish(tmp_path: Path) -> None:
    seed_source_files(tmp_path)
    connection = FakeRereleaseConnection(include_warning_file=True)
    published = False

    async def publisher(write_input: PublishWriteInput) -> PublishWriteResult:
        nonlocal published
        published = True
        return fake_publish_result("PENDING_REVIEW")

    with pytest.raises(SkillLifecycleError, match="error.skill.publish.precheck.confirmRequired"):
        await rerelease_skill_version(FakeEngine(connection), rerelease_input(str(tmp_path)), publish_writer=publisher)

    assert published is False


def test_rerelease_routes_return_java_envelopes(tmp_path: Path) -> None:
    app = create_app()
    seen: list[SkillRereleaseInput] = []

    async def rereleaser(lifecycle_input: SkillRereleaseInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": 77, "action": "RERELEASE_VERSION", "status": "PENDING_REVIEW"}

    app.state.skill_rerelease_writer = rereleaser
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/versions/1.0.0/rerelease",
        json={"targetVersion": " 2.0.0 ", "confirmWarnings": True},
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "rerelease-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["requestId"] == "rerelease-test"
    assert body["data"]["action"] == "RERELEASE_VERSION"
    assert seen[0].version == "1.0.0"
    assert seen[0].target_version == " 2.0.0 "
    assert seen[0].confirm_warnings is True


def test_rerelease_route_supplies_scan_task_publish_writer_when_scanner_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    app.state.db_engine = object()
    app.state.notification_fanout = object()
    app.state.settings = SimpleNamespace(
        storage_base_path=str(tmp_path),
        security_scanner_enabled=True,
        security_scanner_mode="upload",
        redis_url="redis://redis.test:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    seen: dict[str, object] = {}

    async def fake_rerelease(
        engine: object,
        lifecycle_input: SkillRereleaseInput,
        *,
        publish_writer: object | None = None,
        notification_fanout: object | None = None,
    ) -> dict[str, object]:
        seen["engine"] = engine
        seen["scanner_enabled"] = lifecycle_input.scanner_enabled
        seen["scan_mode"] = lifecycle_input.scan_mode
        seen["publish_writer_supplied"] = publish_writer is not None
        seen["notification_fanout_supplied"] = notification_fanout is not None
        return {"skillId": 101, "versionId": 77, "action": "RERELEASE_VERSION", "status": "PENDING_REVIEW"}

    monkeypatch.setattr(lifecycle_api, "rerelease_skill_version", fake_rerelease)
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/versions/1.0.0/rerelease",
        json={"targetVersion": "2.0.0", "confirmWarnings": True},
        headers={"X-Mock-User-Id": "owner"},
    )

    assert response.status_code == 200
    assert seen == {
        "engine": app.state.db_engine,
        "scanner_enabled": True,
        "scan_mode": "upload",
        "publish_writer_supplied": True,
        "notification_fanout_supplied": True,
    }


def test_rerelease_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post(
        "/api/v1/skills/team-a/agent-helper/versions/1.0.0/rerelease",
        json={"targetVersion": "2.0.0", "confirmWarnings": False},
    ).status_code == 401
