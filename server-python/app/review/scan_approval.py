from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

PLATFORM_SCAN_OVERRIDE_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
OVERRIDABLE_LLM_FAILURE_CODES = {"LLM_TIMEOUT", "LLM_UNAVAILABLE"}


@dataclass(frozen=True)
class ScanApprovalEvidence:
    audit_id: int
    scan_status: str
    max_severity: str | None
    analyzers_completed: list[str]
    analyzer_failures: list[dict[str, str]]
    failure_code: str | None
    finding_severities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScanApprovalDecision:
    audit_action: str
    override_detail: dict[str, Any] | None


class ScanApprovalPolicyError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
    return parsed if isinstance(parsed, list) else []


def _completed_analyzers(value: Any) -> list[str]:
    return [str(item) for item in _json_array(value) if isinstance(item, str) and item]


def _analyzer_failures(value: Any) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for item in _json_array(value):
        if not isinstance(item, dict):
            continue
        analyzer = item.get("analyzer")
        code = item.get("code")
        if isinstance(analyzer, str) and isinstance(code, str):
            failures.append({"analyzer": analyzer, "code": code})
    return failures


def _finding_severities(value: Any) -> list[str]:
    severities: list[str] = []
    for item in _json_array(value):
        if not isinstance(item, dict):
            continue
        severity = item.get("severity")
        if isinstance(severity, str) and severity:
            severities.append(severity)
    return severities


async def read_latest_scan_approval_evidence(
    connection: Any,
    *,
    skill_version_id: int,
) -> ScanApprovalEvidence | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT sa.id,
                       sa.max_severity,
                       sa.findings,
                       sa.scanned_at,
                       execution.scan_status,
                       execution.analyzers_completed,
                       execution.analyzer_failures,
                       execution.failure_code
                FROM security_audit sa
                LEFT JOIN local_security_scan_execution execution
                  ON execution.security_audit_id = sa.id
                WHERE sa.skill_version_id = :skill_version_id
                  AND sa.scanner_type = 'SKILL_SCANNER'
                  AND sa.deleted_at IS NULL
                ORDER BY sa.created_at DESC, sa.id DESC
                LIMIT 1
                FOR UPDATE OF sa
                """
            ),
            {"skill_version_id": skill_version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return None

    scan_status = row.get("scan_status") or ("COMPLETE" if row.get("scanned_at") is not None else "PENDING")
    return ScanApprovalEvidence(
        audit_id=int(row["id"]),
        scan_status=str(scan_status),
        max_severity=str(row["max_severity"]) if row.get("max_severity") is not None else None,
        analyzers_completed=_completed_analyzers(row.get("analyzers_completed")),
        analyzer_failures=_analyzer_failures(row.get("analyzer_failures")),
        failure_code=str(row["failure_code"]) if row.get("failure_code") is not None else None,
        finding_severities=_finding_severities(row.get("findings")),
    )


def evaluate_scan_approval(
    evidence: ScanApprovalEvidence | None,
    *,
    platform_roles: set[str],
    confirm_override: bool,
    override_reason: str | None,
    allow_override: bool,
) -> ScanApprovalDecision:
    if evidence is None or evidence.scan_status == "COMPLETE":
        return ScanApprovalDecision("REVIEW_APPROVE", None)
    if evidence.scan_status == "PENDING":
        raise ScanApprovalPolicyError("review.approve.scan_in_progress")
    if evidence.scan_status == "FAILED":
        raise ScanApprovalPolicyError("review.approve.scan_failed")
    if evidence.scan_status != "PARTIAL":
        raise ScanApprovalPolicyError("review.approve.partial_scan_not_overridable")
    if not allow_override:
        raise ScanApprovalPolicyError("review.approve.partial_scan_individual_required")
    if platform_roles.isdisjoint(PLATFORM_SCAN_OVERRIDE_ROLES):
        raise ScanApprovalPolicyError("review.approve.scan_override_forbidden", status_code=403)
    if not confirm_override:
        raise ScanApprovalPolicyError("review.approve.scan_override_confirmation_required")

    reason = override_reason.strip() if override_reason is not None else ""
    if not reason:
        raise ScanApprovalPolicyError("review.approve.scan_override_reason_required")
    if (evidence.max_severity or "").upper() in {"HIGH", "CRITICAL"} or any(
        severity.upper() in {"HIGH", "CRITICAL"} for severity in evidence.finding_severities
    ):
        raise ScanApprovalPolicyError("review.approve.partial_scan_high_risk")
    if "static_analyzer" not in evidence.analyzers_completed:
        raise ScanApprovalPolicyError("review.approve.partial_scan_baseline_incomplete")

    failures = evidence.analyzer_failures
    if not failures or any(
        failure.get("analyzer") != "llm_analyzer"
        or failure.get("code") not in OVERRIDABLE_LLM_FAILURE_CODES
        for failure in failures
    ):
        raise ScanApprovalPolicyError("review.approve.partial_scan_not_overridable")
    if evidence.failure_code not in OVERRIDABLE_LLM_FAILURE_CODES:
        raise ScanApprovalPolicyError("review.approve.partial_scan_not_overridable")

    failure_codes = list(dict.fromkeys(failure["code"] for failure in failures))
    return ScanApprovalDecision(
        audit_action="REVIEW_APPROVE_SCAN_OVERRIDE",
        override_detail={
            "securityAuditId": evidence.audit_id,
            "scanStatus": evidence.scan_status,
            "failureCodes": failure_codes,
            "completedAnalyzers": evidence.analyzers_completed,
            "baselineMaxSeverity": evidence.max_severity,
            "scanOverrideReason": reason,
        },
    )
