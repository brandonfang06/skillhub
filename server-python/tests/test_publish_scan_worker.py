from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.publish.scan_worker import (
    SecurityScanTask,
    StaticScannerClient,
    mark_scan_task_failed,
    parse_scan_task_fields,
    process_scan_task,
    resolve_working_skill_path,
)
from app.publish.scanner_result import AppliedSecurityScanResult, SecurityScanResultInput


class FakeResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> dict[str, object] | None:
        return self.row


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.audit_row = {"id": 801}
        self.version_row = {"id": 202, "status": "SCANNING", "requested_visibility": "PUBLIC"}

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "FROM security_audit" in sql:
            return FakeResult(self.audit_row)
        if "FROM skill_version" in sql:
            return FakeResult(self.version_row)
        return FakeResult()


def test_parse_scan_task_fields_accepts_java_compatible_payload() -> None:
    task = parse_scan_task_fields(
        {
            "taskId": "task-1",
            "versionId": "202",
            "bundleKey": "packages/101/202/bundle.zip",
            "scannerType": "skill-scanner",
            "retryCount": "2",
        }
    )

    assert task == SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
        scanner_type="skill-scanner",
        retry_count=2,
    )


def test_parse_scan_task_fields_rejects_missing_or_invalid_version() -> None:
    assert parse_scan_task_fields({"taskId": "task-1"}) is None
    assert parse_scan_task_fields({"taskId": "task-1", "versionId": "abc"}) is None


def test_resolve_working_skill_path_uses_local_path_without_cleanup() -> None:
    task = SecurityScanTask(task_id="task-1", version_id=202, skill_path="C:/tmp/skill", bundle_key=None)

    resolved = resolve_working_skill_path(task, storage_base_path="C:/storage", scan_temp_dir="C:/tmp/scans")

    assert resolved.skill_path == "C:/tmp/skill"
    assert resolved.cleanup_path is None


def test_resolve_working_skill_path_stages_bundle_and_rejects_traversal(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    task = SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
    )

    resolved = resolve_working_skill_path(task, storage_base_path=str(storage), scan_temp_dir=str(tmp_path / "scans"))

    assert Path(resolved.skill_path).read_bytes() == b"zip-bytes"
    assert resolved.cleanup_path == resolved.skill_path
    assert Path(resolved.skill_path).parent == tmp_path / "scans"

    bad = SecurityScanTask(task_id="task-2", version_id=202, skill_path=None, bundle_key="../secret.zip")
    with pytest.raises(ValueError, match="Unsafe bundle key"):
        resolve_working_skill_path(bad, storage_base_path=str(storage), scan_temp_dir=str(tmp_path / "scans"))


@pytest.mark.anyio
async def test_process_scan_task_calls_scanner_applies_result_and_cleans_bundle(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    task = SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
    )
    scanner = StaticScannerClient(SecurityScanResultInput("scan-1", "SAFE", 0, "LOW", [], 1.0))
    connection = FakeConnection()

    result = await process_scan_task(
        connection,
        task,
        scanner,
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
    )

    assert isinstance(result, AppliedSecurityScanResult)
    assert result.new_status == "PENDING_REVIEW"
    assert scanner.seen_tasks[0].skill_path.endswith(".zip")
    assert not Path(scanner.seen_tasks[0].skill_path).exists()


@pytest.mark.anyio
async def test_mark_scan_task_failed_only_updates_scanning_version() -> None:
    connection = FakeConnection()

    updated = await mark_scan_task_failed(connection, version_id=202)

    assert updated is True
    assert any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)
    assert connection.params[-1] == {"version_id": 202}

    connection = FakeConnection()
    connection.version_row = {"id": 202, "status": "PUBLISHED", "requested_visibility": "PUBLIC"}

    updated = await mark_scan_task_failed(connection, version_id=202)

    assert updated is False
    assert not any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)
