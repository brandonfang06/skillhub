from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.scanner_result import (
    SecurityScanResultInput,
    apply_security_scan_result,
)


class FakeScalarResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row

    def mappings(self) -> FakeScalarResult:
        return self

    def first(self) -> dict[str, object] | None:
        return self.row


MISSING = object()
DEFAULT_TRANSITION = object()


class FakeConnection:
    def __init__(
        self,
        *,
        audit_row: dict[str, object] | None | object = MISSING,
        version_row: dict[str, object] | None = None,
        transition_row: dict[str, object] | None | object = DEFAULT_TRANSITION,
    ) -> None:
        self.audit_row = {"id": 801} if audit_row is MISSING else audit_row
        self.version_row = version_row or {
            "id": 202,
            "status": "SCANNING",
            "requested_visibility": "PUBLIC",
        }
        if transition_row is DEFAULT_TRANSITION:
            next_status = "UPLOADED" if self.version_row["requested_visibility"] == "PRIVATE" else "PENDING_REVIEW"
            self.transition_row: dict[str, object] | None = {"status": next_status}
        else:
            self.transition_row = transition_row
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeScalarResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "FROM security_audit" in sql:
            return FakeScalarResult(self.audit_row)
        if "UPDATE skill_version" in sql and "RETURNING" in sql:
            return FakeScalarResult(self.transition_row)
        if "FROM skill_version" in sql:
            return FakeScalarResult(self.version_row)
        return FakeScalarResult()


def scan_input(**overrides: object) -> SecurityScanResultInput:
    values: dict[str, object] = {
        "scan_id": "scan-123",
        "verdict": "SAFE",
        "findings_count": 0,
        "max_severity": None,
        "findings": [],
        "scan_duration_seconds": 1.25,
        "scanned_at": datetime(2026, 6, 9, 9, 0, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return SecurityScanResultInput(**values)


@pytest.mark.anyio
async def test_apply_scan_result_updates_latest_audit_and_public_scanning_version() -> None:
    connection = FakeConnection()

    result = await apply_security_scan_result(
        connection,
        version_id=202,
        scanner_type="skill-scanner",
        scan_result=scan_input(findings=[{"rule": "ok"}], findings_count=1, max_severity="LOW"),
    )

    assert result.audit_id == 801
    assert result.previous_status == "SCANNING"
    assert result.new_status == "PENDING_REVIEW"
    assert result.status_changed is True
    assert "ORDER BY created_at DESC" in connection.statements[0]
    audit_update_index = next(
        index for index, statement in enumerate(connection.statements) if "UPDATE security_audit" in statement
    )
    audit_params = connection.params[audit_update_index]
    assert audit_params["audit_id"] == 801
    assert audit_params["scan_id"] == "scan-123"
    assert audit_params["verdict"] == "SAFE"
    assert audit_params["is_safe"] is True
    assert audit_params["max_severity"] == "LOW"
    assert audit_params["findings_count"] == 1
    assert json.loads(audit_params["findings"]) == [{"rule": "ok"}]
    assert audit_params["scan_duration_seconds"] == 1.25
    execution_index = next(
        index
        for index, statement in enumerate(connection.statements)
        if "INSERT INTO local_security_scan_execution" in statement
    )
    execution_params = connection.params[execution_index]
    assert execution_params["security_audit_id"] == 801
    assert execution_params["scan_status"] == "COMPLETE"
    assert json.loads(execution_params["analyzers_requested"]) == []
    assert json.loads(execution_params["analyzers_completed"]) == []
    assert json.loads(execution_params["analyzer_failures"]) == []
    assert execution_params["failure_code"] is None

    version_update_index = next(
        index for index, statement in enumerate(connection.statements) if "UPDATE skill_version" in statement
    )
    assert connection.params[version_update_index] == {"version_id": 202}
    assert "AND status = 'SCANNING'" in connection.statements[version_update_index]
    assert "RETURNING status" in connection.statements[version_update_index]


@pytest.mark.anyio
async def test_apply_scan_result_moves_private_scanning_version_to_uploaded() -> None:
    connection = FakeConnection(
        version_row={"id": 202, "status": "SCANNING", "requested_visibility": "PRIVATE"},
    )

    result = await apply_security_scan_result(
        connection,
        version_id=202,
        scanner_type="skill-scanner",
        scan_result=scan_input(verdict="SUSPICIOUS", max_severity="MEDIUM"),
    )

    assert result.new_status == "UPLOADED"
    assert result.status_changed is True
    version_update_index = next(
        index for index, statement in enumerate(connection.statements) if "UPDATE skill_version" in statement
    )
    assert connection.params[version_update_index] == {"version_id": 202}
    audit_update_index = next(
        index for index, statement in enumerate(connection.statements) if "UPDATE security_audit" in statement
    )
    assert connection.params[audit_update_index]["is_safe"] is False


@pytest.mark.anyio
async def test_apply_partial_scan_result_persists_baseline_execution_evidence() -> None:
    connection = FakeConnection()

    result = await apply_security_scan_result(
        connection,
        version_id=202,
        scanner_type="skill-scanner",
        scan_result=scan_input(
            scan_status="PARTIAL",
            analyzers_requested=["static_analyzer", "behavioral_analyzer", "llm_analyzer"],
            analyzers_completed=["static_analyzer", "behavioral_analyzer"],
            analyzer_failures=[{"analyzer": "llm_analyzer", "code": "LLM_TIMEOUT"}],
            failure_code="LLM_TIMEOUT",
        ),
    )

    assert result.new_status == "PENDING_REVIEW"
    execution_index = next(
        index
        for index, statement in enumerate(connection.statements)
        if "INSERT INTO local_security_scan_execution" in statement
    )
    execution_params = connection.params[execution_index]
    assert execution_params["scan_status"] == "PARTIAL"
    assert json.loads(execution_params["analyzers_requested"]) == [
        "static_analyzer",
        "behavioral_analyzer",
        "llm_analyzer",
    ]
    assert json.loads(execution_params["analyzers_completed"]) == ["static_analyzer", "behavioral_analyzer"]
    assert json.loads(execution_params["analyzer_failures"]) == [
        {"analyzer": "llm_analyzer", "code": "LLM_TIMEOUT"}
    ]
    assert execution_params["failure_code"] == "LLM_TIMEOUT"


@pytest.mark.anyio
async def test_apply_scan_result_leaves_published_version_status_untouched() -> None:
    connection = FakeConnection(
        version_row={"id": 202, "status": "PUBLISHED", "requested_visibility": "PUBLIC"},
        transition_row=None,
    )

    result = await apply_security_scan_result(
        connection,
        version_id=202,
        scanner_type="skill-scanner",
        scan_result=scan_input(),
    )

    assert result.previous_status == "PUBLISHED"
    assert result.new_status == "PUBLISHED"
    assert result.status_changed is False
    transition = next(statement for statement in connection.statements if "UPDATE skill_version" in statement)
    assert "AND status = 'SCANNING'" in transition
    assert not any("UPDATE security_audit" in statement for statement in connection.statements)
    assert not any("INSERT INTO local_security_scan_execution" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_apply_scan_result_requires_active_audit() -> None:
    connection = FakeConnection(audit_row=None)

    with pytest.raises(ValueError, match="SecurityAudit not found"):
        await apply_security_scan_result(
            connection,
            version_id=202,
            scanner_type="skill-scanner",
            scan_result=scan_input(),
        )
