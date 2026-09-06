from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Any
from uuid import uuid4

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.publish.scan_contracts import ScanTaskPayload
from app.publish.scan_outbox import enqueue_scan_task


class SecurityScanRetryError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SecurityScanRetryInput:
    skill_id: int
    version_id: int
    user_id: str
    platform_roles: set[str]
    scanner_enabled: bool
    bundle_exists: Callable[[str], bool]
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


async def retry_security_scan(engine: Any, request: SecurityScanRetryInput) -> dict[str, Any]:
    current_time = _now(request.now)
    bundle_key = f"packages/{request.skill_id}/{request.version_id}/bundle.zip"
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT sv.id AS version_id, sv.version, sv.status,
                           s.id AS skill_id, s.owner_id, s.namespace_id,
                           member.role AS namespace_role
                    FROM skill_version sv
                    JOIN skill s ON s.id = sv.skill_id
                    LEFT JOIN namespace_member member
                      ON member.namespace_id = s.namespace_id
                     AND member.user_id = :user_id
                    WHERE sv.id = :version_id AND s.id = :skill_id
                    FOR UPDATE OF sv
                    """
                ),
                {"version_id": request.version_id, "skill_id": request.skill_id, "user_id": request.user_id},
            )
        ).mappings().one_or_none()
        if row is None:
            raise SecurityScanRetryError("error.skill.version.notFound")
        allowed = (
            str(row["owner_id"]) == request.user_id
            or str(row.get("namespace_role") or "") in {"OWNER", "ADMIN"}
            or bool(request.platform_roles & {"SKILL_ADMIN", "SUPER_ADMIN"})
        )
        if not allowed:
            raise SecurityScanRetryError("error.forbidden", status_code=403)
        status = str(row["status"])
        if status not in {"SCAN_FAILED", "SCANNING"}:
            raise SecurityScanRetryError("error.security.scan.retry.status")
        if not request.scanner_enabled:
            raise SecurityScanRetryError("error.security.scan.retry.disabled")

        active = (
            await connection.execute(
                text(
                    """
                    SELECT sa.id, sa.task_id
                    FROM security_audit sa
                    LEFT JOIN local_security_scan_execution execution
                      ON execution.security_audit_id = sa.id
                    WHERE sa.skill_version_id = :version_id
                      AND sa.scanner_type = 'SKILL_SCANNER'
                      AND sa.deleted_at IS NULL
                      AND sa.scanned_at IS NULL
                      AND COALESCE(execution.scan_status, 'PENDING') = 'PENDING'
                    ORDER BY sa.created_at DESC, sa.id DESC
                    LIMIT 1
                    """
                ),
                {"version_id": request.version_id},
            )
        ).mappings().one_or_none()
        if status == "SCANNING" and active is not None:
            return {
                "skillId": request.skill_id,
                "versionId": request.version_id,
                "action": "RETRY_SECURITY_SCAN",
                "status": "SCANNING",
                "taskId": str(active["task_id"]),
            }
        if status != "SCAN_FAILED":
            raise SecurityScanRetryError("error.security.scan.retry.status")
        if not request.bundle_exists(bundle_key):
            raise SecurityScanRetryError("error.security.scan.retry.bundleMissing")

        task_id = str(uuid4())
        audit_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO security_audit (
                            skill_version_id, scanner_type, verdict, is_safe,
                            findings_count, findings, task_id, failure_reason, created_at
                        ) VALUES (
                            :version_id, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE,
                            0, CAST(:findings AS JSONB), :task_id, NULL, :created_at
                        ) RETURNING id
                        """
                    ),
                    {"version_id": request.version_id, "findings": json.dumps([]), "task_id": task_id, "created_at": current_time},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO local_security_scan_execution (
                    security_audit_id, scan_status, analyzers_requested,
                    analyzers_completed, analyzer_failures
                ) VALUES (:audit_id, 'PENDING', '[]', '[]', '[]')
                """
            ),
            {"audit_id": audit_id},
        )
        task = ScanTaskPayload(
            task_id=task_id,
            version_id=request.version_id,
            skill_path=None,
            bundle_key=bundle_key,
            publisher_id=request.user_id,
            created_at_millis=int(current_time.timestamp() * 1000),
            metadata={"scannerType": "skill-scanner", "retry": "true"},
            request_id=request.request_id,
        )
        await enqueue_scan_task(connection, task, next_attempt_at=current_time, request_id=request.request_id)
        await connection.execute(text("UPDATE skill_version SET status = 'SCANNING' WHERE id = :version_id"), {"version_id": request.version_id})
        await write_audit_log(
            connection,
            actor_user_id=request.user_id,
            action="RETRY_SECURITY_SCAN",
            target_type="SKILL_VERSION",
            target_id=request.version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail={"taskId": task_id, "version": str(row["version"])},
            created_at=current_time,
        )
    return {"skillId": request.skill_id, "versionId": request.version_id, "action": "RETRY_SECURITY_SCAN", "status": "SCANNING", "taskId": task_id}
