from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.replacement import (
    ReplaceableVersion,
    StorageDeleteCompensationInput,
    cleanup_replaceable_version,
    delete_local_storage_objects,
    delete_local_storage_objects_or_record_compensation,
    record_storage_delete_compensation,
)


@dataclass
class FakeResult:
    rows: list[dict[str, Any]] | None = None

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []


class FakeConnection:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.results = results or []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "SELECT storage_key" in sql and self.results:
            return self.results.pop(0)
        return FakeResult()


def replaceable_version(*, status: str = "UPLOADED", latest_version_id: int | None = None) -> ReplaceableVersion:
    return ReplaceableVersion(
        skill_id=7,
        namespace="global",
        slug="agent-helper",
        version_id=42,
        version="1.0.0",
        status=status,
        latest_version_id=latest_version_id,
        now=datetime(2026, 6, 8, 16, 17, 18, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_cleanup_rejects_published_version() -> None:
    connection = FakeConnection()

    with pytest.raises(ValueError, match="Version already published: 1.0.0"):
        await cleanup_replaceable_version(connection, replaceable_version(status="PUBLISHED"))

    assert connection.statements == []


@pytest.mark.anyio
async def test_cleanup_clears_latest_version_before_delete() -> None:
    connection = FakeConnection([FakeResult(rows=[])])

    await cleanup_replaceable_version(connection, replaceable_version(latest_version_id=42))

    assert "UPDATE skill" in connection.statements[0]
    assert "latest_version_id = NULL" in connection.statements[0]
    assert connection.params[0]["skill_id"] == 7
    assert "DELETE FROM skill_version" in connection.statements[-1]


@pytest.mark.anyio
async def test_cleanup_deletes_review_files_security_audits_and_version() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    {"storage_key": "skills/7/42/SKILL.md"},
                    {"storage_key": ""},
                    {"storage_key": None},
                    {"storage_key": "skills/7/42/src/main.py"},
                ]
            )
        ]
    )

    result = await cleanup_replaceable_version(connection, replaceable_version())

    assert result.storage_keys == [
        "skills/7/42/SKILL.md",
        "skills/7/42/src/main.py",
        "packages/7/42/bundle.zip",
    ]
    assert any("DELETE FROM review_task" in statement for statement in connection.statements)
    assert any("DELETE FROM skill_file" in statement for statement in connection.statements)
    assert any("UPDATE security_audit" in statement and "deleted_at" in statement for statement in connection.statements)
    assert "DELETE FROM skill_version" in connection.statements[-1]


def test_delete_local_storage_objects_removes_existing_files(tmp_path) -> None:
    file_path = tmp_path / "skills" / "7" / "42" / "SKILL.md"
    bundle_path = tmp_path / "packages" / "7" / "42" / "bundle.zip"
    file_path.parent.mkdir(parents=True)
    bundle_path.parent.mkdir(parents=True)
    file_path.write_text("skill", encoding="utf-8")
    bundle_path.write_bytes(b"zip")

    deleted = delete_local_storage_objects(
        str(tmp_path),
        ["skills/7/42/SKILL.md", "packages/7/42/bundle.zip", "missing/object.txt"],
    )

    assert deleted == ["skills/7/42/SKILL.md", "packages/7/42/bundle.zip"]
    assert not file_path.exists()
    assert not bundle_path.exists()


def test_delete_local_storage_objects_rejects_escape(tmp_path) -> None:
    with pytest.raises(ValueError, match="Object key escapes storage base"):
        delete_local_storage_objects(str(tmp_path), ["../outside.txt"])


@pytest.mark.anyio
async def test_record_storage_delete_compensation_inserts_pending_record() -> None:
    connection = FakeConnection()

    await record_storage_delete_compensation(
        connection,
        StorageDeleteCompensationInput(
            skill_id=7,
            namespace="global",
            slug="agent-helper",
            storage_keys=["skills/7/42/SKILL.md", "packages/7/42/bundle.zip"],
            last_error="disk locked",
            now=datetime(2026, 6, 8, 16, 17, 18, tzinfo=UTC),
        ),
    )

    assert "INSERT INTO skill_storage_delete_compensation" in connection.statements[0]
    assert connection.params[0]["status"] == "PENDING"
    assert connection.params[0]["attempt_count"] == 0
    assert connection.params[0]["storage_keys_json"] == '["skills/7/42/SKILL.md","packages/7/42/bundle.zip"]'
    assert connection.params[0]["last_error"] == "disk locked"


@pytest.mark.anyio
async def test_failed_local_delete_records_compensation(tmp_path) -> None:
    connection = FakeConnection()

    result = await delete_local_storage_objects_or_record_compensation(
        connection,
        str(tmp_path),
        StorageDeleteCompensationInput(
            skill_id=7,
            namespace="global",
            slug="agent-helper",
            storage_keys=["../outside.txt"],
            last_error=None,
            now=datetime(2026, 6, 8, 16, 17, 18, tzinfo=UTC),
        ),
    )

    assert result.deleted_keys == []
    assert result.compensation_recorded is True
    assert "INSERT INTO skill_storage_delete_compensation" in connection.statements[0]
    assert "Object key escapes storage base" in str(connection.params[0]["last_error"])
