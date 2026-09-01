from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish import replacement as replacement_module
from app.publish.replacement import (
    ReplaceableVersion,
    find_replaceable_version,
    StorageDeleteCompensationInput,
    cleanup_replaceable_version,
    delete_local_storage_objects,
    delete_local_storage_objects_or_record_compensation,
    record_storage_delete_compensation,
)


@dataclass
class FakeResult:
    rows: list[dict[str, Any]] | None = None
    row: dict[str, Any] | None = None

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class FakeConnection:
    def __init__(
        self,
        results: list[FakeResult] | None = None,
        *,
        current_status: str = "UPLOADED",
        rejected_review: dict[str, Any] | None = None,
        file_rows: list[dict[str, Any]] | None = None,
        scanner_rows: list[dict[str, Any]] | None = None,
        locked_row: dict[str, Any] | None = None,
    ) -> None:
        self.results = results or []
        self.current_status = current_status
        self.rejected_review = rejected_review
        self.file_rows = file_rows
        self.scanner_rows = scanner_rows or []
        self.locked_row = locked_row
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "FOR UPDATE OF s, sv" in sql:
            return FakeResult(
                row=self.locked_row
                or {
                    "status": self.current_status,
                    "version": "1.0.0",
                    "skill_id": 7,
                    "slug": "agent-helper",
                    "owner_id": "local-user",
                    "skill_status": "ACTIVE",
                    "namespace_slug": "global",
                    "namespace_status": "ACTIVE",
                    "has_pending_review": False,
                }
            )
        if "FROM review_task rt" in sql:
            return FakeResult(row=self.rejected_review)
        if "FROM skill_file" in sql and self.file_rows is not None:
            return FakeResult(rows=self.file_rows)
        if "FROM security_audit" in sql:
            return FakeResult(rows=self.scanner_rows)
        if self.results and ("FROM skill_file" in sql or "FROM skill s" in sql):
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
        publisher_id="local-user",
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
async def test_cleanup_archives_rejected_version_before_deleting_active_rows() -> None:
    connection = FakeConnection(
        current_status="REJECTED",
        file_rows=[
            {
                "file_path": "SKILL.md",
                "file_size": 42,
                "content_type": "text/markdown",
                "sha256": "abc123",
                "storage_key": "skills/7/42/SKILL.md",
            }
        ],
        rejected_review={
            "review_task_id": 91,
            "namespace_id": 10,
            "submitted_by": "local-user",
            "reviewed_by": "reviewer-1",
            "review_comment": "Fix the metadata",
            "submitted_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
            "reviewed_at": datetime(2026, 6, 7, 11, 0, tzinfo=UTC),
            "parsed_metadata_json": {"name": "Agent Helper", "version": "1.0.0"},
            "manifest_json": [{"path": "SKILL.md", "size": 42}],
            "original_request_id": "reject-request",
        },
        scanner_rows=[
            {
                "scanner_type": "STATIC",
                "verdict": "PASS",
                "max_severity": "LOW",
                "findings_count": 0,
                "findings": [],
                "created_at": datetime(2026, 6, 7, 10, 30, tzinfo=UTC),
            }
        ],
    )

    result = await cleanup_replaceable_version(connection, replaceable_version(status="REJECTED"))

    assert result.archived_review is not None
    assert result.archived_review.original_review_task_id == 91
    assert result.archived_review.original_skill_version_id == 42
    assert result.archived_review.review_comment == "Fix the metadata"
    assert result.archived_review.files == [
        {
            "path": "SKILL.md",
            "size": 42,
            "contentType": "text/markdown",
            "sha256": "abc123",
        }
    ]
    assert result.archived_review.scanner_summary[0]["scannerType"] == "STATIC"
    review_delete = next(sql for sql in connection.statements if "DELETE FROM review_task" in sql)
    assert "status = 'PENDING'" not in review_delete
    assert "DELETE FROM skill_version" in connection.statements[-1]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("current_status", "message"),
    [
        ("PUBLISHED", "Version already published: 1.0.0"),
        ("YANKED", "Version cannot be replaced from status YANKED"),
        ("PENDING_REVIEW", "Version cannot be replaced from status PENDING_REVIEW"),
    ],
)
async def test_cleanup_rechecks_ineligible_status_inside_transaction_before_deleting(
    current_status: str,
    message: str,
) -> None:
    connection = FakeConnection(current_status=current_status)

    with pytest.raises(ValueError, match=message):
        await cleanup_replaceable_version(connection, replaceable_version(status="UPLOADED"))

    assert len(connection.statements) == 1
    assert "FOR UPDATE OF s, sv" in connection.statements[0]
    assert connection.params[0] == {"version_id": 42}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("locked_override", "message"),
    [
        ({"owner_id": "other-user"}, "Replacement owner changed"),
        ({"slug": "other-skill"}, "Replacement coordinates changed"),
        ({"namespace_slug": "other-namespace"}, "Replacement coordinates changed"),
        ({"version": "2.0.0"}, "Replacement coordinates changed"),
        ({"skill_status": "ARCHIVED"}, "Skill is not writable"),
        ({"namespace_status": "FROZEN"}, "Namespace is not writable"),
        ({"has_pending_review": True}, "Skill already has a pending review"),
    ],
)
async def test_cleanup_rechecks_rejected_replacement_invariants_before_deleting(
    locked_override: dict[str, Any],
    message: str,
) -> None:
    locked_row = {
        "status": "REJECTED",
        "version": "1.0.0",
        "skill_id": 7,
        "slug": "agent-helper",
        "owner_id": "local-user",
        "skill_status": "ACTIVE",
        "namespace_slug": "global",
        "namespace_status": "ACTIVE",
        "has_pending_review": False,
        **locked_override,
    }
    connection = FakeConnection(current_status="REJECTED", locked_row=locked_row)

    with pytest.raises(ValueError, match=message):
        await cleanup_replaceable_version(connection, replaceable_version(status="REJECTED"))

    assert len(connection.statements) == 1
    assert not any(statement.lstrip().startswith("DELETE") for statement in connection.statements)


@pytest.mark.anyio
async def test_cleanup_clears_latest_version_before_delete() -> None:
    connection = FakeConnection([FakeResult(rows=[])])

    await cleanup_replaceable_version(connection, replaceable_version(latest_version_id=42))

    update_index = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill" in sql)
    assert "latest_version_id = NULL" in connection.statements[update_index]
    assert connection.params[update_index]["skill_id"] == 7
    assert connection.params[update_index]["publisher_id"] == "local-user"
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
    assert any("DELETE FROM scan_task_outbox" in statement for statement in connection.statements)
    assert any("DELETE FROM skill_file" in statement for statement in connection.statements)
    assert any("UPDATE security_audit" in statement and "deleted_at" in statement for statement in connection.statements)
    assert "DELETE FROM skill_version" in connection.statements[-1]
    assert result.archived_review is None


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


def test_delete_local_storage_objects_uses_object_storage_adapter(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    fake_object_storage_factory,
) -> None:
    storage = fake_object_storage_factory(
        {
            "skills/7/42/SKILL.md": b"skill",
            "packages/7/42/bundle.zip": b"zip",
        }
    )
    monkeypatch.setattr(replacement_module, "object_storage_for_base_path", lambda storage_base_path: storage)

    deleted = delete_local_storage_objects(
        str(tmp_path / "missing-local-storage"),
        ["skills/7/42/SKILL.md", "packages/7/42/bundle.zip", "missing/object.txt"],
    )

    assert deleted == ["skills/7/42/SKILL.md", "packages/7/42/bundle.zip"]
    assert storage.deleted_keys == ["skills/7/42/SKILL.md", "packages/7/42/bundle.zip"]
    assert not (tmp_path / "missing-local-storage").exists()


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


@pytest.mark.anyio
async def test_find_replaceable_version_maps_existing_non_published_version() -> None:
    connection = FakeConnection(
        [
            FakeResult(
                row={
                    "skill_id": 7,
                    "namespace": "global",
                    "slug": "agent-helper",
                    "version_id": 41,
                    "version": "1.0.0",
                    "status": "UPLOADED",
                    "latest_version_id": 41,
                }
            )
        ]
    )

    result = await find_replaceable_version(
        connection,
        namespace_id=10,
        namespace="global",
        slug="agent-helper",
        version="1.0.0",
        publisher_id="local-user",
        now=datetime(2026, 6, 9, 8, 1, 2, tzinfo=UTC),
    )

    assert result == ReplaceableVersion(
        skill_id=7,
        namespace="global",
        slug="agent-helper",
        version_id=41,
        version="1.0.0",
        status="UPLOADED",
        publisher_id="local-user",
        latest_version_id=41,
        now=datetime(2026, 6, 9, 8, 1, 2, tzinfo=UTC),
    )
    assert "FROM skill s" in connection.statements[0]
    assert "JOIN skill_version sv" in connection.statements[0]
    assert connection.params[0] == {
        "namespace_id": 10,
        "slug": "agent-helper",
        "version": "1.0.0",
        "publisher_id": "local-user",
    }


@pytest.mark.anyio
async def test_find_replaceable_version_returns_none_without_match() -> None:
    connection = FakeConnection([FakeResult(row=None)])

    result = await find_replaceable_version(
        connection,
        namespace_id=10,
        namespace="global",
        slug="agent-helper",
        version="1.0.0",
        publisher_id="local-user",
    )

    assert result is None
