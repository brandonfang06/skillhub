from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.package import PackageEntry, SkillMetadata
from app.publish.storage import SkillFileWriteRecord, StoredPackageResult
from app.publish.transaction import (
    PublishDbTransactionInput,
    PublishDbFinalizeInput,
    PublishDbPrepareInput,
    build_manifest_json,
    build_parsed_metadata_json,
    create_publish_db_records,
    determine_initial_version_status,
    finalize_publish_db_records,
    prepare_publish_db_records,
)


def package_entries() -> list[PackageEntry]:
    return [
        PackageEntry("SKILL.md", b"# Demo\n", "text/markdown"),
        PackageEntry("src/main.py", b"print('ok')\n", "text/x-python"),
    ]


def storage_result(version_id: int = 42) -> StoredPackageResult:
    files = [
        SkillFileWriteRecord(
            version_id=version_id,
            file_path="SKILL.md",
            file_size=7,
            content_type="text/markdown",
            sha256="1" * 64,
            storage_key="skills/7/42/SKILL.md",
        ),
        SkillFileWriteRecord(
            version_id=version_id,
            file_path="src/main.py",
            file_size=12,
            content_type="text/x-python",
            sha256="2" * 64,
            storage_key="skills/7/42/src/main.py",
        ),
    ]
    return StoredPackageResult(
        files=files,
        bundle_key="packages/7/42/bundle.zip",
        bundle_size=200,
        file_count=2,
        total_size=19,
        bundle_ready=True,
        download_ready=True,
    )


def transaction_input(*, auto_publish: bool = False, visibility: str = "PUBLIC") -> PublishDbTransactionInput:
    return PublishDbTransactionInput(
        namespace_id=10,
        slug="agent-helper",
        display_name="Agent Helper",
        summary="Helps agents",
        publisher_id="local-user",
        visibility=visibility,
        version="1.0.0",
        auto_publish=auto_publish,
        metadata=SkillMetadata(
            name="Agent Helper",
            description="Helps agents",
            version="1.0.0",
            frontmatter={"name": "Agent Helper", "description": "Helps agents", "version": "1.0.0"},
        ),
        entries=package_entries(),
        stored_package=storage_result(),
        now=datetime(2026, 6, 8, 12, 30, 45, tzinfo=UTC),
    )


def prepare_input(*, auto_publish: bool = False, visibility: str = "PUBLIC") -> PublishDbPrepareInput:
    base = transaction_input(auto_publish=auto_publish, visibility=visibility)
    return PublishDbPrepareInput(
        namespace_id=base.namespace_id,
        slug=base.slug,
        display_name=base.display_name,
        summary=base.summary,
        publisher_id=base.publisher_id,
        visibility=base.visibility,
        version=base.version,
        auto_publish=base.auto_publish,
        metadata=base.metadata,
        entries=base.entries,
        now=base.now,
    )


def test_determine_initial_version_status() -> None:
    assert determine_initial_version_status(auto_publish=True, visibility="PUBLIC") == "PUBLISHED"
    assert determine_initial_version_status(auto_publish=False, visibility="PRIVATE") == "UPLOADED"
    assert determine_initial_version_status(auto_publish=False, visibility="PUBLIC") == "PENDING_REVIEW"
    assert determine_initial_version_status(auto_publish=False, visibility="NAMESPACE_ONLY") == "PENDING_REVIEW"


def test_build_manifest_json_matches_java_shape() -> None:
    assert build_manifest_json(package_entries()) == [
        {"path": "SKILL.md", "size": 7, "contentType": "text/markdown"},
        {"path": "src/main.py", "size": 12, "contentType": "text/x-python"},
    ]


def test_build_parsed_metadata_json_keeps_frontmatter() -> None:
    metadata = transaction_input().metadata

    assert build_parsed_metadata_json(metadata) == {
        "name": "Agent Helper",
        "description": "Helps agents",
        "version": "1.0.0",
    }


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        return self.results.pop(0)


class FakeTransactionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeTransactionContext:
        return FakeTransactionContext(self.connection)


@pytest.mark.anyio
async def test_prepare_publish_db_records_encodes_jsonb_parameters_for_asyncpg() -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
        ]
    )

    await prepare_publish_db_records(connection, prepare_input(auto_publish=True))
    version_params = connection.params[2]

    assert isinstance(version_params["parsed_metadata_json"], str)
    assert isinstance(version_params["manifest_json"], str)
    assert json.loads(version_params["parsed_metadata_json"]) == build_parsed_metadata_json(transaction_input().metadata)
    assert json.loads(version_params["manifest_json"]) == build_manifest_json(package_entries())


@pytest.mark.anyio
async def test_create_publish_db_records_inserts_new_skill_version_files_and_updates_stats() -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
            FakeResult(rows=[]),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
        ]
    )

    result = await create_publish_db_records(FakeEngine(connection), transaction_input(auto_publish=True))

    assert result.skill_id == 7
    assert result.version_id == 42
    assert result.version_status == "PUBLISHED"
    assert result.latest_version_updated
    assert result.file_count == 2
    assert result.total_size == 19
    assert "SELECT id, status" in connection.statements[0]
    assert "INSERT INTO skill" in connection.statements[1]
    assert "INSERT INTO skill_version" in connection.statements[2]
    assert connection.params[2]["status"] == "PUBLISHED"
    assert connection.params[2]["published_at"] == datetime(2026, 6, 8, 12, 30, 45, tzinfo=UTC)
    assert "INSERT INTO skill_file" in connection.statements[3]
    assert connection.params[3]["file_path"] == "SKILL.md"
    assert connection.params[4]["file_path"] == "src/main.py"
    assert "UPDATE skill_version" in connection.statements[5]
    assert connection.params[5]["bundle_ready"] is True
    assert connection.params[5]["download_ready"] is True
    assert "UPDATE skill" in connection.statements[6]
    assert connection.params[6]["latest_version_id"] == 42


@pytest.mark.anyio
async def test_prepare_publish_db_records_creates_version_without_file_rows() -> None:
    connection = FakeConnection(
        [
            FakeResult(row=None),
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(scalar=42),
        ]
    )

    result = await prepare_publish_db_records(connection, prepare_input(auto_publish=True))

    assert result.skill_id == 7
    assert result.version_id == 42
    assert result.version_status == "PUBLISHED"
    assert result.latest_version_updated is True
    assert "SELECT id, status" in connection.statements[0]
    assert "INSERT INTO skill" in connection.statements[1]
    assert "INSERT INTO skill_version" in connection.statements[2]
    assert not any("INSERT INTO skill_file" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_finalize_publish_db_records_inserts_files_stats_and_skill_metadata() -> None:
    connection = FakeConnection([FakeResult(), FakeResult(), FakeResult(), FakeResult()])

    await finalize_publish_db_records(
        connection,
        PublishDbFinalizeInput(
            skill_id=7,
            version_id=42,
            display_name="Agent Helper",
            summary="Helps agents",
            publisher_id="local-user",
            visibility="PUBLIC",
            latest_version_updated=True,
            stored_package=storage_result(),
            now=datetime(2026, 6, 8, 12, 30, 45, tzinfo=UTC),
        ),
    )

    assert "INSERT INTO skill_file" in connection.statements[0]
    assert connection.params[0]["file_path"] == "SKILL.md"
    assert "INSERT INTO skill_file" in connection.statements[1]
    assert connection.params[1]["file_path"] == "src/main.py"
    assert "UPDATE skill_version" in connection.statements[2]
    assert connection.params[2]["file_count"] == 2
    assert connection.params[2]["total_size"] == 19
    assert "UPDATE skill" in connection.statements[3]
    assert connection.params[3]["latest_version_id"] == 42


@pytest.mark.anyio
async def test_create_publish_db_records_reuses_existing_skill_without_insert() -> None:
    connection = FakeConnection(
        [
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(rows=[]),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
        ]
    )

    result = await create_publish_db_records(FakeEngine(connection), transaction_input(visibility="PRIVATE"))

    assert result.skill_id == 7
    assert result.version_status == "UPLOADED"
    assert result.latest_version_updated
    assert not any("INSERT INTO skill (" in statement for statement in connection.statements)
    assert any(params.get("status") == "UPLOADED" for params in connection.params)


@pytest.mark.anyio
async def test_create_publish_db_records_rejects_archived_skill_before_version_insert() -> None:
    connection = FakeConnection([FakeResult(row={"id": 7, "status": "ARCHIVED"})])

    with pytest.raises(ValueError, match="Cannot publish to archived skill: agent-helper"):
        await create_publish_db_records(FakeEngine(connection), transaction_input())

    assert len(connection.statements) == 1


@pytest.mark.anyio
async def test_create_publish_db_records_leaves_latest_version_for_pending_review() -> None:
    connection = FakeConnection(
        [
            FakeResult(row={"id": 7, "status": "ACTIVE"}),
            FakeResult(rows=[]),
            FakeResult(scalar=42),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
        ]
    )

    result = await create_publish_db_records(FakeEngine(connection), transaction_input())

    assert result.version_status == "PENDING_REVIEW"
    assert not result.latest_version_updated
    assert all("latest_version_id" not in params for params in connection.params)
    assert "UPDATE skill" in connection.statements[-1]
