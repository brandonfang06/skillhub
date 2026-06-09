from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class SecurityScanResultInput:
    scan_id: str
    verdict: str
    findings_count: int
    max_severity: str | None
    findings: list[dict[str, Any]]
    scan_duration_seconds: float
    scanned_at: datetime | None = None


@dataclass(frozen=True)
class AppliedSecurityScanResult:
    audit_id: int
    previous_status: str
    new_status: str
    status_changed: bool


def status_after_scan_result(current_status: str, requested_visibility: str | None) -> str:
    if current_status != "SCANNING":
        return current_status
    if requested_visibility == "PRIVATE":
        return "UPLOADED"
    return "PENDING_REVIEW"


async def apply_security_scan_result(
    connection: Any,
    *,
    version_id: int,
    scanner_type: str,
    scan_result: SecurityScanResultInput,
) -> AppliedSecurityScanResult:
    audit_row = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM security_audit
                WHERE skill_version_id = :version_id
                  AND scanner_type = :scanner_type
                  AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"version_id": version_id, "scanner_type": scanner_type},
        )
    ).mappings().first()
    if audit_row is None:
        raise ValueError(f"SecurityAudit not found for versionId={version_id}, scannerType={scanner_type}")

    version_row = (
        await connection.execute(
            text(
                """
                SELECT id, status, requested_visibility
                FROM skill_version
                WHERE id = :version_id
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().first()
    if version_row is None:
        raise ValueError(f"SkillVersion not found: {version_id}")

    scanned_at = scan_result.scanned_at or datetime.now(UTC)
    await connection.execute(
        text(
            """
            UPDATE security_audit
            SET scan_id = :scan_id,
                verdict = :verdict,
                is_safe = :is_safe,
                max_severity = :max_severity,
                findings_count = :findings_count,
                findings = :findings,
                scan_duration_seconds = :scan_duration_seconds,
                scanned_at = :scanned_at
            WHERE id = :audit_id
            """
        ),
        {
            "audit_id": int(audit_row["id"]),
            "scan_id": scan_result.scan_id,
            "verdict": scan_result.verdict,
            "is_safe": scan_result.verdict == "SAFE",
            "max_severity": scan_result.max_severity,
            "findings_count": scan_result.findings_count,
            "findings": json.dumps(scan_result.findings, separators=(",", ":")),
            "scan_duration_seconds": scan_result.scan_duration_seconds,
            "scanned_at": scanned_at,
        },
    )

    previous_status = str(version_row["status"])
    new_status = status_after_scan_result(previous_status, version_row.get("requested_visibility"))
    if new_status != previous_status:
        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status
                WHERE id = :version_id
                """
            ),
            {"version_id": version_id, "status": new_status},
        )

    return AppliedSecurityScanResult(
        audit_id=int(audit_row["id"]),
        previous_status=previous_status,
        new_status=new_status,
        status_changed=new_status != previous_status,
    )
