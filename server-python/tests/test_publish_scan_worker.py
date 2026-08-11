from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from app.core.request_id import request_id_scope
from app.publish.scan_worker import (
    ScanTaskAlreadyFinalized,
    ScanTaskLeaseUnavailable,
    ScanTaskNotReady,
    SecurityScanTask,
    StaticScannerClient,
    mark_scan_task_failed,
    parse_scan_task_fields,
    process_scan_task,
    resolve_working_skill_path,
)
from app.publish.scanner_result import (
    AppliedSecurityScanResult,
    SecurityScanResultInput,
)


class FakeResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, object] | None:
        return self.row


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.audit_row = {"id": 801}
        self.version_row = {"id": 202, "status": "SCANNING", "requested_visibility": "PUBLIC"}
        self.lease_acquired = True
        self.failure_transition_row: dict[str, object] | None = {"id": 202}

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "pg_try_advisory_xact_lock" in sql:
            return FakeResult({"acquired": self.lease_acquired})
        if "FROM security_audit" in sql:
            return FakeResult(self.audit_row)
        if "UPDATE skill_version" in sql and "SCAN_FAILED" in sql and "RETURNING" in sql:
            return FakeResult(self.failure_transition_row)
        if "UPDATE skill_version" in sql and "RETURNING status" in sql:
            status = "UPLOADED" if self.version_row["requested_visibility"] == "PRIVATE" else "PENDING_REVIEW"
            return FakeResult({"status": status})
        if "FROM skill_version" in sql:
            return FakeResult(self.version_row)
        return FakeResult()


class FakeObjectStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def put_bytes(self, key: str, content: bytes, *, content_type: str | None = None) -> None:
        self.objects[key] = content

    def read_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete_many(self, keys: list[str]) -> list[str]:
        deleted: list[str] = []
        for key in keys:
            if key in self.objects:
                del self.objects[key]
                deleted.append(key)
        return deleted


def test_parse_scan_task_fields_accepts_java_compatible_payload() -> None:
    task = parse_scan_task_fields(
        {
            "taskId": "task-1",
            "versionId": "202",
            "bundleKey": "packages/101/202/bundle.zip",
            "scannerType": "skill-scanner",
            "retryCount": "2",
            "createdAtMillis": "1780968000000",
            "visibilityRetryCount": "4",
        }
    )

    assert task == SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
        scanner_type="skill-scanner",
        retry_count=2,
        created_at_millis=1780968000000,
        visibility_retry_count=4,
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
async def test_process_scan_task_does_not_scan_without_database_lease(tmp_path: Path) -> None:
    connection = FakeConnection()
    connection.lease_acquired = False
    scanner = StaticScannerClient(SecurityScanResultInput("scan-1", "SAFE", 0, None, [], 1.0))

    with pytest.raises(ScanTaskLeaseUnavailable):
        await process_scan_task(
            connection,
            SecurityScanTask(task_id="task-busy", version_id=202, skill_path=str(tmp_path)),
            scanner,
            storage_base_path=str(tmp_path),
            scan_temp_dir=str(tmp_path / "scans"),
        )

    assert scanner.seen_tasks == []


@pytest.mark.anyio
async def test_process_scan_task_skips_version_that_is_no_longer_scanning(tmp_path: Path) -> None:
    connection = FakeConnection()
    connection.version_row = {"id": 202, "status": "PUBLISHED", "requested_visibility": "PUBLIC"}
    scanner = StaticScannerClient(SecurityScanResultInput("scan-1", "SAFE", 0, None, [], 1.0))

    with pytest.raises(ScanTaskAlreadyFinalized):
        await process_scan_task(
            connection,
            SecurityScanTask(task_id="task-finalized", version_id=202, skill_path=str(tmp_path)),
            scanner,
            storage_base_path=str(tmp_path),
            scan_temp_dir=str(tmp_path / "scans"),
        )

    assert scanner.seen_tasks == []


@pytest.mark.anyio
async def test_process_scan_task_leaves_uncommitted_version_for_reclaim(tmp_path: Path) -> None:
    connection = FakeConnection()
    connection.version_row = None
    scanner = StaticScannerClient(SecurityScanResultInput("scan-1", "SAFE", 0, None, [], 1.0))

    with pytest.raises(ScanTaskNotReady):
        await process_scan_task(
            connection,
            SecurityScanTask(task_id="task-not-ready", version_id=202, skill_path=str(tmp_path)),
            scanner,
            storage_base_path=str(tmp_path),
            scan_temp_dir=str(tmp_path / "scans"),
        )

    assert scanner.seen_tasks == []


@pytest.mark.anyio
async def test_process_scan_task_logs_applied_result(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    scanner = StaticScannerClient(
        SecurityScanResultInput(
            "scan-1",
            "SAFE",
            0,
            "LOW",
            [],
            1.0,
            scan_status="PARTIAL",
            failure_code="LLM_TIMEOUT",
        )
    )
    connection = FakeConnection()
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    with request_id_scope("worker-log-request"):
        await process_scan_task(
            connection,
            task,
            scanner,
            storage_base_path=str(storage),
            scan_temp_dir=str(tmp_path / "scans"),
        )

    assert "scan.task.completed" in caplog.text
    assert "task_id=task-1" in caplog.text
    assert "version_id=202" in caplog.text
    assert "scan_id=scan-1" in caplog.text
    assert "verdict=SAFE" in caplog.text
    assert "audit_id=801" in caplog.text
    assert "previous_status=SCANNING" in caplog.text
    assert "new_status=PENDING_REVIEW" in caplog.text
    assert "failure_code=LLM_TIMEOUT" in caplog.text
    assert "request_id=worker-log-request" in caplog.text


@pytest.mark.anyio
async def test_process_scan_task_reads_bundle_from_object_storage(tmp_path: Path) -> None:
    task = SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
    )
    storage = FakeObjectStorage({"packages/101/202/bundle.zip": b"zip-bytes"})
    scanner = StaticScannerClient(SecurityScanResultInput("scan-1", "SAFE", 0, "LOW", [], 1.0))
    connection = FakeConnection()

    result = await process_scan_task(
        connection,
        task,
        scanner,
        storage_base_path="unused-for-object-storage",
        scan_temp_dir=str(tmp_path / "scans"),
        storage=storage,
    )

    assert isinstance(result, AppliedSecurityScanResult)
    assert scanner.seen_tasks[0].bundle_key == "packages/101/202/bundle.zip"
    assert scanner.seen_tasks[0].skill_path.endswith(".zip")
    assert not Path(scanner.seen_tasks[0].skill_path).exists()


@pytest.mark.anyio
async def test_process_scan_task_marks_failed_when_final_retry_cannot_stage_bundle(tmp_path: Path) -> None:
    connection = FakeConnection()
    task = SecurityScanTask(
        task_id="task-missing-bundle",
        version_id=202,
        bundle_key="packages/101/202/missing.zip",
    )

    with pytest.raises(FileNotFoundError):
        await process_scan_task(
            connection,
            task,
            StaticScannerClient(SecurityScanResultInput("unused", "SAFE", 0, None, [], 0.0)),
            storage_base_path=str(tmp_path / "storage"),
            scan_temp_dir=str(tmp_path / "scans"),
            mark_failed_on_error=True,
        )

    assert any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_mark_scan_task_failed_only_updates_scanning_version() -> None:
    connection = FakeConnection()

    updated = await mark_scan_task_failed(
        connection,
        version_id=202,
        scanner_type="skill-scanner",
        failure_code="SCANNER_UNAVAILABLE",
    )

    assert updated is True
    assert any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)
    execution_index = next(
        index
        for index, statement in enumerate(connection.statements)
        if "INSERT INTO local_security_scan_execution" in statement
    )
    assert connection.params[execution_index]["security_audit_id"] == 801
    assert connection.params[execution_index]["scan_status"] == "FAILED"
    assert connection.params[execution_index]["failure_code"] == "SCANNER_UNAVAILABLE"

    connection = FakeConnection()
    connection.version_row = {"id": 202, "status": "PUBLISHED", "requested_visibility": "PUBLIC"}
    connection.failure_transition_row = None

    updated = await mark_scan_task_failed(connection, version_id=202)

    assert updated is False
    transition = next(statement for statement in connection.statements if "UPDATE skill_version" in statement)
    assert "AND status = 'SCANNING'" in transition
    assert not any("INSERT INTO local_security_scan_execution" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_mark_scan_task_failed_does_not_overwrite_evidence_after_lost_race() -> None:
    connection = FakeConnection()
    connection.failure_transition_row = None

    updated = await mark_scan_task_failed(connection, version_id=202)

    assert updated is False
    transition = next(statement for statement in connection.statements if "UPDATE skill_version" in statement)
    assert "AND status = 'SCANNING'" in transition
    assert "RETURNING id" in transition
    assert not any("INSERT INTO local_security_scan_execution" in statement for statement in connection.statements)
