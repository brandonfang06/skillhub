from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text

from app.object_storage import ObjectStorage
from app.publish.scanner_result import AppliedSecurityScanResult, SecurityScanResultInput, apply_security_scan_result


@dataclass(frozen=True)
class SecurityScanTask:
    task_id: str | None
    version_id: int
    skill_path: str | None = None
    bundle_key: str | None = None
    scanner_type: str = "skill-scanner"
    retry_count: int = 0


@dataclass(frozen=True)
class ResolvedScanPath:
    skill_path: str
    cleanup_path: str | None


class ScannerClient(Protocol):
    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        pass


class StaticScannerClient:
    def __init__(self, result: SecurityScanResultInput) -> None:
        self.result = result
        self.seen_tasks: list[SecurityScanTask] = []

    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        self.seen_tasks.append(
            SecurityScanTask(
                task_id=task.task_id,
                version_id=task.version_id,
                skill_path=skill_path,
                bundle_key=task.bundle_key,
                scanner_type=task.scanner_type,
                retry_count=task.retry_count,
            )
        )
        return self.result


def blank_to_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value


def parse_retry_count(fields: dict[str, str]) -> int:
    raw = blank_to_none(fields.get("retryCount"))
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def parse_scan_task_fields(fields: dict[str, str]) -> SecurityScanTask | None:
    raw_version_id = blank_to_none(fields.get("versionId"))
    if raw_version_id is None:
        return None
    try:
        version_id = int(raw_version_id)
    except ValueError:
        return None

    return SecurityScanTask(
        task_id=blank_to_none(fields.get("taskId")),
        version_id=version_id,
        skill_path=blank_to_none(fields.get("skillPath")),
        bundle_key=blank_to_none(fields.get("bundleKey")),
        scanner_type=blank_to_none(fields.get("scannerType")) or "skill-scanner",
        retry_count=parse_retry_count(fields),
    )


def resolve_safe_child(base: Path, relative_path: str) -> Path:
    normalized_base = base.resolve()
    resolved = (normalized_base / relative_path).resolve()
    try:
        resolved.relative_to(normalized_base)
    except ValueError as exc:
        raise ValueError(f"Unsafe bundle key: {relative_path}") from exc
    return resolved


def stage_bundle_bytes(task: SecurityScanTask, bundle: bytes, *, scan_temp_dir: str) -> ResolvedScanPath:
    temp_dir = Path(scan_temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / f"{task.version_id}-{task.task_id or 'scan'}.zip"
    target.write_bytes(bundle)
    return ResolvedScanPath(skill_path=str(target), cleanup_path=str(target))


def resolve_working_skill_path(
    task: SecurityScanTask,
    *,
    storage_base_path: str,
    scan_temp_dir: str,
    storage: ObjectStorage | None = None,
) -> ResolvedScanPath:
    if task.bundle_key is None:
        if task.skill_path is None:
            raise ValueError("Security scan task missing skillPath and bundleKey")
        return ResolvedScanPath(skill_path=task.skill_path, cleanup_path=None)

    if storage is not None:
        resolve_safe_child(Path(scan_temp_dir), task.bundle_key)
        return stage_bundle_bytes(task, storage.read_bytes(task.bundle_key), scan_temp_dir=scan_temp_dir)

    source = resolve_safe_child(Path(storage_base_path), task.bundle_key)
    if not source.exists():
        raise FileNotFoundError(f"Scan bundle not found: {task.bundle_key}")
    return stage_bundle_bytes(task, source.read_bytes(), scan_temp_dir=scan_temp_dir)


def cleanup_scan_path(path: str | None, *, scan_temp_dir: str) -> None:
    if path is None:
        return
    base = Path(scan_temp_dir).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists():
        target.unlink()


async def process_scan_task(
    connection: Any,
    task: SecurityScanTask,
    scanner: ScannerClient,
    *,
    storage_base_path: str,
    scan_temp_dir: str,
    storage: ObjectStorage | None = None,
    mark_failed_on_error: bool = True,
) -> AppliedSecurityScanResult:
    resolved = resolve_working_skill_path(
        task,
        storage_base_path=storage_base_path,
        scan_temp_dir=scan_temp_dir,
        storage=storage,
    )
    try:
        scan_result = await scanner.scan(task, resolved.skill_path)
        return await apply_security_scan_result(
            connection,
            version_id=task.version_id,
            scanner_type=task.scanner_type,
            scan_result=scan_result,
        )
    except Exception:
        if mark_failed_on_error:
            await mark_scan_task_failed(connection, version_id=task.version_id)
        raise
    finally:
        cleanup_scan_path(resolved.cleanup_path, scan_temp_dir=scan_temp_dir)


async def mark_scan_task_failed(connection: Any, *, version_id: int) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, status
                FROM skill_version
                WHERE id = :version_id
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().first()
    if row is None or row["status"] != "SCANNING":
        return False

    await connection.execute(
        text(
            """
            UPDATE skill_version
            SET status = 'SCAN_FAILED'
            WHERE id = :version_id
            """
        ),
        {"version_id": version_id},
    )
    return True
