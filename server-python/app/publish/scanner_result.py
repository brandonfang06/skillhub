from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


def scanner_type_db_value(scanner_type: str) -> str:
    if scanner_type == "skill-scanner":
        return "SKILL_SCANNER"
    return scanner_type


@dataclass(frozen=True)
class SecurityScanResultInput:
    scan_id: str
    verdict: str
    findings_count: int
    max_severity: str | None
    findings: list[dict[str, Any]]
    scan_duration_seconds: float
    scanned_at: datetime | None = None
    scan_status: str = "COMPLETE"
    analyzers_requested: list[str] = field(default_factory=list)
    analyzers_completed: list[str] = field(default_factory=list)
    analyzer_failures: list[dict[str, str]] = field(default_factory=list)
    failure_code: str | None = None


@dataclass(frozen=True)
class AppliedSecurityScanResult:
    audit_id: int
    previous_status: str
    new_status: str
    status_changed: bool


async def upsert_scan_execution(
    connection: Any,
    *,
    security_audit_id: int,
    scan_status: str,
    analyzers_requested: list[str],
    analyzers_completed: list[str],
    analyzer_failures: list[dict[str, str]],
    failure_code: str | None,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO local_security_scan_execution (
                security_audit_id,
                scan_status,
                analyzers_requested,
                analyzers_completed,
                analyzer_failures,
                failure_code
            ) VALUES (
                :security_audit_id,
                :scan_status,
                :analyzers_requested,
                :analyzers_completed,
                :analyzer_failures,
                :failure_code
            )
            ON CONFLICT (security_audit_id) DO UPDATE
            SET scan_status = EXCLUDED.scan_status,
                analyzers_requested = EXCLUDED.analyzers_requested,
                analyzers_completed = EXCLUDED.analyzers_completed,
                analyzer_failures = EXCLUDED.analyzer_failures,
                failure_code = EXCLUDED.failure_code,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "security_audit_id": security_audit_id,
            "scan_status": scan_status,
            "analyzers_requested": json.dumps(analyzers_requested, separators=(",", ":")),
            "analyzers_completed": json.dumps(analyzers_completed, separators=(",", ":")),
            "analyzer_failures": json.dumps(analyzer_failures, separators=(",", ":")),
            "failure_code": failure_code,
        },
    )


async def apply_security_scan_result(
    connection: Any,
    *,
    version_id: int,
    scanner_type: str,
    scan_result: SecurityScanResultInput,
) -> AppliedSecurityScanResult:
    db_scanner_type = scanner_type_db_value(scanner_type)
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
            {"version_id": version_id, "scanner_type": db_scanner_type},
        )
    ).mappings().first()
    if audit_row is None:
        raise ValueError(f"SecurityAudit not found for versionId={version_id}, scannerType={scanner_type}")

    transition_row = (
        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = CASE
                    WHEN requested_visibility = 'PRIVATE' THEN 'UPLOADED'
                    ELSE 'PENDING_REVIEW'
                END
                WHERE id = :version_id
                  AND status = 'SCANNING'
                RETURNING status
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().first()
    if transition_row is None:
        version_row = (
            await connection.execute(
                text("SELECT status FROM skill_version WHERE id = :version_id"),
                {"version_id": version_id},
            )
        ).mappings().first()
        if version_row is None:
            raise ValueError(f"SkillVersion not found: {version_id}")
        current_status = str(version_row["status"])
        return AppliedSecurityScanResult(
            audit_id=int(audit_row["id"]),
            previous_status=current_status,
            new_status=current_status,
            status_changed=False,
        )

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
    await upsert_scan_execution(
        connection,
        security_audit_id=int(audit_row["id"]),
        scan_status=scan_result.scan_status,
        analyzers_requested=scan_result.analyzers_requested,
        analyzers_completed=scan_result.analyzers_completed,
        analyzer_failures=scan_result.analyzer_failures,
        failure_code=scan_result.failure_code,
    )

    return AppliedSecurityScanResult(
        audit_id=int(audit_row["id"]),
        previous_status="SCANNING",
        new_status=str(transition_row["status"]),
        status_changed=True,
    )
