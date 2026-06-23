from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata
from app.publish.replacement import ReplaceableVersion


def package_entries() -> list[PackageEntry]:
    return [
        PackageEntry("SKILL.md", b"# Demo\n", "text/markdown"),
        PackageEntry("src/main.py", b"print('ok')\n", "text/x-python"),
    ]


def publish_input(storage_base_path: str, *, visibility: str = "PUBLIC") -> PublishWriteInput:
    return PublishWriteInput(
        namespace_id=10,
        namespace_slug="global",
        slug="agent-helper",
        display_name="Agent Helper",
        summary="Helps agents",
        publisher_id="local-user",
        visibility=visibility,
        version="1.0.0",
        auto_publish=False,
        metadata=SkillMetadata(
            name="Agent Helper",
            description="Helps agents",
            version="1.0.0",
            frontmatter={"name": "Agent Helper", "description": "Helps agents", "version": "1.0.0"},
        ),
        entries=package_entries(),
        storage_base_path=storage_base_path,
        scanner_enabled=False,
        now=datetime(2026, 6, 8, 18, 19, 20, tzinfo=UTC),
    )


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def scalar_one(self) -> Any:
        return self.scalar


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        sql = str(statement)
        if "status = 'PENDING_REVIEW'" in sql:
            return FakeResult(rows=[])
        if "FROM user_role_binding" in sql and "SKILL_ADMIN" in sql:
            return FakeResult(rows=[{"user_id": "local-user"}, {"user_id": "platform-admin"}])
        if "FROM namespace_member nm" in sql and "notification_preference" in sql:
            return FakeResult(rows=[{"user_id": "team-admin"}, {"user_id": "local-user"}])
        if "INSERT INTO notification" in sql:
            values = params or {}
            row = {
                "id": 7000 + len(self.notifications),
                "recipient_id": values["recipient_id"],
                "category": values["category"],
                "event_type": values["event_type"],
                "title": values["title"],
                "body_json": values["body_json"],
                "entity_type": values["entity_type"],
                "entity_id": values["entity_id"],
                "created_at": values["created_at"],
            }
            self.notifications.append(row)
            return FakeResult(rows=[row])
        if self.results:
            return self.results.pop(0)
        return FakeResult()


class FakeTransactionContext:
    def __init__(self, connection: FakeConnection, engine: "FakeEngine") -> None:
        self.connection = connection
        self.engine = engine

    async def __aenter__(self) -> FakeConnection:
        self.engine.entered_connections.append(self.connection)
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.engine.exit_exc_types.append(exc_type)
        return None


class FakeEngine:
    def __init__(self, connections: list[FakeConnection]) -> None:
        self.connections = connections
        self.entered_connections: list[FakeConnection] = []
        self.exit_exc_types: list[Any] = []

    def begin(self) -> FakeTransactionContext:
        return FakeTransactionContext(self.connections.pop(0), self)


class FakeScanTaskPublisher:
    def __init__(self) -> None:
        self.tasks: list[Any] = []

    async def publish_scan_task(self, task: Any) -> None:
        self.tasks.append(task)


class FakeNotificationFanout:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.published.append((user_id, payload))


class AutoWithdrawFakeConnection(FakeConnection):
    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "SELECT id, status" in sql and "FROM skill" in sql:
            return FakeResult(row={"id": 7, "status": "ACTIVE"})
        if "status = 'PENDING_REVIEW'" in sql:
            return FakeResult(rows=[{"id": 41}])
        if "INSERT INTO skill_version" in sql:
            return FakeResult(scalar=42)
        if "INSERT INTO review_task" in sql:
            return FakeResult(scalar=900)
        return FakeResult()


@pytest.mark.anyio
async def test_execute_publish_write_prepares_storage_finalizes_and_applies_side_effects(tmp_path) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar=900),
        ]
    )

    result = await execute_publish_write(FakeEngine([connection]), publish_input(str(tmp_path)))

    assert result.skill_id == 7
    assert result.version_id == 42
    assert result.version_status == "PENDING_REVIEW"
    assert result.stored_package.file_count == 2
    assert result.side_effects.review_task_id == 900
    assert result.replacement_deleted_keys == []
    assert not result.replacement_compensation_recorded
    assert (tmp_path / "skills" / "7" / "42" / "SKILL.md").read_bytes() == b"# Demo\n"
    assert (tmp_path / "packages" / "7" / "42" / "bundle.zip").exists()
    assert "SELECT id, status" in connection.statements[0]
    assert "INSERT INTO skill" in connection.statements[1]
    assert "INSERT INTO skill_version" in connection.statements[2]
    assert "INSERT INTO skill_file" in connection.statements[3]
    assert "UPDATE skill_version" in connection.statements[5]
    assert "UPDATE skill" in connection.statements[6]
    assert "INSERT INTO review_task" in connection.statements[7]


@pytest.mark.anyio
async def test_execute_publish_write_uses_supplied_object_storage(
    tmp_path,
    fake_object_storage_factory,
) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar=900),
        ]
    )
    storage = fake_object_storage_factory()
    request = replace(publish_input(str(tmp_path / "missing-local-storage")), storage=storage)

    result = await execute_publish_write(FakeEngine([connection]), request)

    assert result.stored_package.bundle_key == "packages/7/42/bundle.zip"
    assert storage.objects["skills/7/42/SKILL.md"] == b"# Demo\n"
    assert storage.objects["skills/7/42/src/main.py"] == b"print('ok')\n"
    assert storage.objects["packages/7/42/bundle.zip"].startswith(b"PK")
    assert not (tmp_path / "missing-local-storage").exists()


@pytest.mark.anyio
async def test_execute_publish_write_runs_after_publish_callback_in_same_transaction(tmp_path) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar=900),
        ]
    )
    seen: list[tuple[FakeConnection, int, int, int]] = []

    async def callback(callback_connection: Any, skill_id: int, version_id: int) -> None:
        seen.append((callback_connection, skill_id, version_id, len(callback_connection.statements)))

    await execute_publish_write(FakeEngine([connection]), publish_input(str(tmp_path)), after_publish=callback)

    assert seen == [(connection, 7, 42, 8)]
    assert "INSERT INTO review_task" in connection.statements[7]


@pytest.mark.anyio
async def test_execute_publish_write_notifies_reviewers_when_review_task_created(tmp_path) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar=900),
        ]
    )
    fanout = FakeNotificationFanout()

    await execute_publish_write(
        FakeEngine([connection]),
        publish_input(str(tmp_path)),
        notification_fanout=fanout,
    )

    assert {row["recipient_id"] for row in connection.notifications} == {"local-user", "platform-admin", "team-admin"}
    assert {row["event_type"] for row in connection.notifications} == {"REVIEW_SUBMITTED"}
    body = json.loads(connection.notifications[0]["body_json"])
    assert body["reviewId"] == 900
    assert body["skillId"] == 7
    assert body["versionId"] == 42
    assert body["submitterId"] == "local-user"
    assert body["namespace"] == "global"
    assert body["slug"] == "agent-helper"
    assert body["skillName"] == "Agent Helper"
    assert {recipient for recipient, _payload in fanout.published} == {"local-user", "platform-admin", "team-admin"}
    assert {payload["eventType"] for _recipient, payload in fanout.published} == {"REVIEW_SUBMITTED"}


@pytest.mark.anyio
async def test_execute_publish_write_publishes_scan_task_when_scanner_enabled(tmp_path) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar=900),
            FakeResult(scalar=801),
            FakeResult(),
        ]
    )
    publisher = FakeScanTaskPublisher()

    result = await execute_publish_write(
        FakeEngine([connection]),
        PublishWriteInput(
            namespace_id=10,
            namespace_slug="global",
            slug="agent-helper",
            display_name="Agent Helper",
            summary="Helps agents",
            publisher_id="local-user",
            visibility="PUBLIC",
            version="1.0.0",
            auto_publish=False,
            metadata=SkillMetadata(
                name="Agent Helper",
                description="Helps agents",
                version="1.0.0",
                frontmatter={"name": "Agent Helper", "description": "Helps agents", "version": "1.0.0"},
            ),
            entries=package_entries(),
            storage_base_path=str(tmp_path),
            scanner_enabled=True,
            scan_mode="upload",
            task_id="scan-task-1",
            now=datetime(2026, 6, 8, 18, 19, 20, tzinfo=UTC),
        ),
        scan_task_publisher=publisher,
    )

    assert result.side_effects.scan_task is not None
    assert publisher.tasks == [result.side_effects.scan_task]
    assert publisher.tasks[0].bundle_key == "packages/7/42/bundle.zip"
    assert publisher.tasks[0].skill_path is None


@pytest.mark.anyio
async def test_execute_publish_write_auto_withdraws_pending_review_before_new_version(tmp_path) -> None:
    connection = AutoWithdrawFakeConnection([])

    result = await execute_publish_write(FakeEngine([connection]), publish_input(str(tmp_path)))

    assert result.version_id == 42
    withdraw_select = next(index for index, statement in enumerate(connection.statements) if "status = 'PENDING_REVIEW'" in statement)
    withdraw_delete = next(index for index, statement in enumerate(connection.statements) if "DELETE FROM review_task" in statement)
    withdraw_update = next(index for index, statement in enumerate(connection.statements) if "status = 'UPLOADED'" in statement)
    version_insert = next(index for index, statement in enumerate(connection.statements) if "INSERT INTO skill_version" in statement)
    assert withdraw_select < withdraw_delete < withdraw_update < version_insert
    assert connection.params[withdraw_update]["version_ids"] == [41]
    assert "updated_by" not in connection.params[withdraw_update]


@pytest.mark.anyio
async def test_execute_publish_write_deletes_replacement_storage_after_commit(tmp_path) -> None:
    old_file = tmp_path / "skills" / "7" / "41" / "SKILL.md"
    old_bundle = tmp_path / "packages" / "7" / "41" / "bundle.zip"
    old_file.parent.mkdir(parents=True)
    old_bundle.parent.mkdir(parents=True)
    old_file.write_text("old", encoding="utf-8")
    old_bundle.write_bytes(b"old-bundle")

    write_connection = FakeConnection(
        [
            FakeResult(),
            FakeResult(),
            FakeResult(rows=[{"storage_key": "skills/7/41/SKILL.md"}]),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
        ]
    )
    cleanup_connection = FakeConnection([])
    engine = FakeEngine([write_connection, cleanup_connection])

    result = await execute_publish_write(
        engine,
        publish_input(str(tmp_path), visibility="PRIVATE").with_replacement(
            ReplaceableVersion(
                skill_id=7,
                namespace="global",
                slug="agent-helper",
                version_id=41,
                version="1.0.0",
                status="UPLOADED",
                publisher_id="local-user",
                latest_version_id=41,
                now=datetime(2026, 6, 8, 18, 19, 20, tzinfo=UTC),
            )
        ),
    )

    assert len(engine.entered_connections) == 2
    assert result.replacement_deleted_keys == ["skills/7/41/SKILL.md", "packages/7/41/bundle.zip"]
    assert not result.replacement_compensation_recorded
    assert not old_file.exists()
    assert not old_bundle.exists()
    update_skill_index = next(index for index, statement in enumerate(write_connection.statements) if "UPDATE skill" in statement)
    delete_old_version_index = next(index for index, statement in enumerate(write_connection.statements) if "DELETE FROM skill_version" in statement)
    insert_new_version_index = next(index for index, statement in enumerate(write_connection.statements) if "INSERT INTO skill_version" in statement)
    assert update_skill_index < delete_old_version_index < insert_new_version_index
    assert cleanup_connection.statements == []


@pytest.mark.anyio
async def test_execute_publish_write_aborts_finalize_when_storage_write_fails(tmp_path) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
        ]
    )
    engine = FakeEngine([connection])
    request = publish_input(str(tmp_path))
    request = PublishWriteInput(
        namespace_id=request.namespace_id,
        namespace_slug=request.namespace_slug,
        slug=request.slug,
        display_name=request.display_name,
        summary=request.summary,
        publisher_id=request.publisher_id,
        visibility=request.visibility,
        version=request.version,
        auto_publish=request.auto_publish,
        metadata=request.metadata,
        entries=[PackageEntry("../outside.txt", b"escape", "text/plain")],
        storage_base_path=request.storage_base_path,
        scanner_enabled=request.scanner_enabled,
        now=request.now,
    )

    with pytest.raises(ValueError, match="Parent directory paths are not allowed"):
        await execute_publish_write(engine, request)

    assert engine.exit_exc_types == [ValueError]
    assert len(engine.entered_connections) == 1
    assert "INSERT INTO skill_version" in connection.statements[2]
    assert not any("INSERT INTO skill_file" in statement for statement in connection.statements)
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)
    assert not any("INSERT INTO review_task" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_execute_publish_write_rolls_back_transaction_when_storage_writer_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
        ]
    )
    engine = FakeEngine([connection])

    def failing_storage_writer(*args: object, **kwargs: object) -> object:
        raise OSError("simulated storage failure")

    monkeypatch.setattr(
        "app.publish.orchestration.write_local_package_objects",
        failing_storage_writer,
    )

    with pytest.raises(OSError, match="simulated storage failure"):
        await execute_publish_write(engine, publish_input(str(tmp_path)))

    assert engine.exit_exc_types == [OSError]
    assert "INSERT INTO skill_version" in connection.statements[2]
    assert not any("INSERT INTO skill_file" in statement for statement in connection.statements)
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)
    assert not any("INSERT INTO review_task" in statement for statement in connection.statements)
    assert not any("INSERT INTO security_audit" in statement for statement in connection.statements)
