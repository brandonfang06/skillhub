from __future__ import annotations

import pytest

from app.review.scan_approval import (
    ScanApprovalEvidence,
    ScanApprovalPolicyError,
    evaluate_scan_approval,
)


def partial_evidence(**overrides: object) -> ScanApprovalEvidence:
    values: dict[str, object] = {
        "audit_id": 801,
        "scan_status": "PARTIAL",
        "max_severity": "MEDIUM",
        "analyzers_completed": ["static_analyzer", "behavioral_analyzer"],
        "analyzer_failures": [{"analyzer": "llm_analyzer", "code": "LLM_TIMEOUT"}],
        "failure_code": "LLM_TIMEOUT",
    }
    values.update(overrides)
    return ScanApprovalEvidence(**values)


def test_no_audit_or_complete_scan_uses_normal_approval() -> None:
    no_audit = evaluate_scan_approval(
        None,
        platform_roles=set(),
        confirm_override=False,
        override_reason=None,
        allow_override=True,
    )
    complete = evaluate_scan_approval(
        partial_evidence(scan_status="COMPLETE", failure_code=None, analyzer_failures=[]),
        platform_roles=set(),
        confirm_override=False,
        override_reason=None,
        allow_override=True,
    )

    assert no_audit.audit_action == "REVIEW_APPROVE"
    assert complete.audit_action == "REVIEW_APPROVE"
    assert no_audit.override_detail is None
    assert complete.override_detail is None


@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        ("PENDING", "review.approve.scan_in_progress"),
        ("FAILED", "review.approve.scan_failed"),
    ],
)
def test_pending_and_failed_scans_are_never_approvable(status: str, error_code: str) -> None:
    with pytest.raises(ScanApprovalPolicyError, match=error_code):
        evaluate_scan_approval(
            partial_evidence(scan_status=status),
            platform_roles={"SUPER_ADMIN"},
            confirm_override=True,
            override_reason="Reviewed baseline",
            allow_override=True,
        )


def test_eligible_partial_scan_requires_platform_reviewer_confirmation_and_reason() -> None:
    decision = evaluate_scan_approval(
        partial_evidence(),
        platform_roles={"SKILL_ADMIN"},
        confirm_override=True,
        override_reason="  Provider outage; baseline evidence reviewed.  ",
        allow_override=True,
    )

    assert decision.audit_action == "REVIEW_APPROVE_SCAN_OVERRIDE"
    assert decision.override_detail == {
        "securityAuditId": 801,
        "scanStatus": "PARTIAL",
        "failureCodes": ["LLM_TIMEOUT"],
        "completedAnalyzers": ["static_analyzer", "behavioral_analyzer"],
        "baselineMaxSeverity": "MEDIUM",
        "scanOverrideReason": "Provider outage; baseline evidence reviewed.",
    }


@pytest.mark.parametrize(
    ("roles", "confirm", "reason", "allow_override", "error_code", "status_code"),
    [
        (set(), True, "reviewed", True, "review.approve.scan_override_forbidden", 403),
        ({"SKILL_ADMIN"}, False, "reviewed", True, "review.approve.scan_override_confirmation_required", 400),
        ({"SKILL_ADMIN"}, True, "   ", True, "review.approve.scan_override_reason_required", 400),
        ({"SKILL_ADMIN"}, True, "reviewed", False, "review.approve.partial_scan_individual_required", 400),
    ],
)
def test_partial_override_rejects_missing_authority_or_explicit_consent(
    roles: set[str],
    confirm: bool,
    reason: str,
    allow_override: bool,
    error_code: str,
    status_code: int,
) -> None:
    with pytest.raises(ScanApprovalPolicyError, match=error_code) as error:
        evaluate_scan_approval(
            partial_evidence(),
            platform_roles=roles,
            confirm_override=confirm,
            override_reason=reason,
            allow_override=allow_override,
        )

    assert error.value.status_code == status_code


@pytest.mark.parametrize(
    ("evidence", "error_code"),
    [
        (partial_evidence(max_severity="HIGH"), "review.approve.partial_scan_high_risk"),
        (partial_evidence(max_severity="CRITICAL"), "review.approve.partial_scan_high_risk"),
        (
            partial_evidence(max_severity=None, finding_severities=["HIGH"]),
            "review.approve.partial_scan_high_risk",
        ),
        (
            partial_evidence(analyzers_completed=["behavioral_analyzer"]),
            "review.approve.partial_scan_baseline_incomplete",
        ),
        (
            partial_evidence(
                analyzer_failures=[{"analyzer": "static_analyzer", "code": "SCANNER_ERROR"}],
                failure_code="SCANNER_ERROR",
            ),
            "review.approve.partial_scan_not_overridable",
        ),
        (
            partial_evidence(
                analyzer_failures=[{"analyzer": "llm_analyzer", "code": "LLM_ERROR"}],
                failure_code="LLM_ERROR",
            ),
            "review.approve.partial_scan_not_overridable",
        ),
    ],
)
def test_partial_override_rejects_unsafe_or_ambiguous_evidence(
    evidence: ScanApprovalEvidence,
    error_code: str,
) -> None:
    with pytest.raises(ScanApprovalPolicyError, match=error_code):
        evaluate_scan_approval(
            evidence,
            platform_roles={"SUPER_ADMIN"},
            confirm_override=True,
            override_reason="reviewed",
            allow_override=True,
        )
