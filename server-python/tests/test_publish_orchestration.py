from __future__ import annotations

from dataclasses import dataclass
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

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
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
        return None


class FakeEngine:
    def __init__(self, connections: list[FakeConnection]) -> None:
        self.connections = connections
        self.entered_connections: list[FakeConnection] = []

    def begin(self) -> FakeTransactionContext:
        return FakeTransactionContext(self.connections.pop(0), self)


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
    assert "UPDATE skill" in write_connection.statements[0]
    assert "DELETE FROM skill_version" in write_connection.statements[5]
    assert "INSERT INTO skill_version" in write_connection.statements[7]
    assert cleanup_connection.statements == []
