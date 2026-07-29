from __future__ import annotations

import json
from pathlib import Path

import pytest

from scanner_adapter.errors import ScannerResponseError
from scanner_adapter.normalize import normalize_scan_response

FIXTURES = Path(__file__).parent / "fixtures"
REQUIRED_TOP_LEVEL_FIELDS = (
    "scan_id",
    "skill_name",
    "is_safe",
    "max_severity",
    "findings_count",
    "scan_duration_seconds",
    "timestamp",
    "findings",
)


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_normalize_safe_response() -> None:
    raw = load_fixture("safe_response.json")

    result = normalize_scan_response(raw, analyzers_requested=("static", "aidefense"))

    assert result.normalized.to_dict() == {
        "schema_version": "1",
        "scan_id": "72bcbd2e-d8af-4eb8-92ea-32c834679247",
        "skill_name": "safe-example",
        "is_safe": True,
        "max_severity": "INFO",
        "findings_count": 0,
        "scan_duration_seconds": 0.42,
        "analyzers_requested": ["static", "aidefense"],
        "findings": [],
    }


def test_normalize_unsafe_response_and_findings() -> None:
    raw = load_fixture("unsafe_response.json")

    result = normalize_scan_response(
        raw,
        analyzers_requested=("static", "behavioral", "aidefense"),
    )

    assert result.normalized.is_safe is False
    assert result.normalized.to_dict()["findings"] == [
        {
            "rule_id": "RULE-001",
            "severity": "HIGH",
            "category": "data-exfiltration",
            "title": "Potential data exfiltration",
            "description": "Description from the scanner",
            "file_path": "scripts/run.py",
            "line_number": 12,
            "remediation": "Review the outbound request",
            "analyzer": "aidefense",
        }
    ]


def test_normalize_sets_optional_finding_fields_to_none() -> None:
    raw = load_fixture("unsafe_response.json")
    finding = raw["findings"][0]
    assert isinstance(finding, dict)
    for field in ("file_path", "line_number", "remediation", "analyzer"):
        finding.pop(field)

    result = normalize_scan_response(raw, analyzers_requested=("static",))

    normalized_finding = result.normalized.to_dict()["findings"][0]
    assert normalized_finding["file_path"] is None
    assert normalized_finding["line_number"] is None
    assert normalized_finding["remediation"] is None
    assert normalized_finding["analyzer"] is None


def test_normalize_ignores_unknown_fields() -> None:
    raw = load_fixture("safe_response.json")
    raw["future_top_level_field"] = {"anything": True}

    result = normalize_scan_response(raw, analyzers_requested=("static",))

    assert "future_top_level_field" not in result.normalized.to_dict()


@pytest.mark.parametrize("field", REQUIRED_TOP_LEVEL_FIELDS)
def test_normalize_rejects_missing_required_field(field: str) -> None:
    raw = load_fixture("safe_response.json")
    raw.pop(field)

    with pytest.raises(ScannerResponseError, match=field):
        normalize_scan_response(raw, analyzers_requested=("static",))


def test_normalize_rejects_wrong_findings_shape() -> None:
    raw = load_fixture("safe_response.json")
    raw["findings"] = {"not": "a list"}

    with pytest.raises(ScannerResponseError, match="findings"):
        normalize_scan_response(raw, analyzers_requested=("static",))


def test_normalize_rejects_mismatched_findings_count() -> None:
    raw = load_fixture("unsafe_response.json")
    raw["findings_count"] = 2

    with pytest.raises(ScannerResponseError, match="findings_count"):
        normalize_scan_response(raw, analyzers_requested=("static",))


def test_result_preserves_raw_response_in_memory() -> None:
    raw = load_fixture("safe_response.json")
    raw["future_top_level_field"] = "kept for library callers"

    result = normalize_scan_response(raw, analyzers_requested=("static",))

    assert result.raw_response is raw
    assert result.raw_response["future_top_level_field"] == "kept for library callers"
