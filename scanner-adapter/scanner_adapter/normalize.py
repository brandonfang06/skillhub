"""Normalize the Cisco Skill Scanner HTTP response."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import cast

from scanner_adapter.errors import ScannerResponseError
from scanner_adapter.models import NormalizedFinding, NormalizedScan, ScanResult


def normalize_scan_response(
    raw_response: Mapping[str, object],
    *,
    analyzers_requested: tuple[str, ...],
) -> ScanResult:
    findings_value = _required(raw_response, "findings")
    if not isinstance(findings_value, list):
        raise ScannerResponseError("response field 'findings' must be a list")

    findings = tuple(
        _normalize_finding(item, index=index)
        for index, item in enumerate(findings_value)
    )
    findings_count = _required_int(raw_response, "findings_count", minimum=0)
    if findings_count != len(findings):
        raise ScannerResponseError(
            "response field 'findings_count' does not match the findings list"
        )

    _required_str(raw_response, "timestamp")
    normalized = NormalizedScan(
        scan_id=_required_str(raw_response, "scan_id"),
        skill_name=_required_str(raw_response, "skill_name"),
        is_safe=_required_bool(raw_response, "is_safe"),
        max_severity=_required_str(raw_response, "max_severity"),
        findings_count=findings_count,
        scan_duration_seconds=_required_number(
            raw_response,
            "scan_duration_seconds",
            minimum=0,
        ),
        analyzers_requested=analyzers_requested,
        findings=findings,
    )
    return ScanResult(normalized=normalized, raw_response=raw_response)


def _normalize_finding(value: object, *, index: int) -> NormalizedFinding:
    if not isinstance(value, Mapping):
        raise ScannerResponseError(f"response finding at index {index} must be an object")
    finding = cast(Mapping[str, object], value)
    return NormalizedFinding(
        rule_id=_required_str(finding, "rule_id", prefix=f"findings[{index}]"),
        severity=_required_str(finding, "severity", prefix=f"findings[{index}]"),
        category=_required_str(finding, "category", prefix=f"findings[{index}]"),
        title=_required_str(finding, "title", prefix=f"findings[{index}]"),
        description=_required_str(
            finding,
            "description",
            prefix=f"findings[{index}]",
        ),
        file_path=_optional_str(finding, "file_path", prefix=f"findings[{index}]"),
        line_number=_optional_int(
            finding,
            "line_number",
            prefix=f"findings[{index}]",
        ),
        remediation=_optional_str(
            finding,
            "remediation",
            prefix=f"findings[{index}]",
        ),
        analyzer=_optional_str(finding, "analyzer", prefix=f"findings[{index}]"),
    )


def _required(mapping: Mapping[str, object], field: str) -> object:
    if field not in mapping:
        raise ScannerResponseError(f"response is missing required field '{field}'")
    return mapping[field]


def _required_str(
    mapping: Mapping[str, object],
    field: str,
    *,
    prefix: str = "response",
) -> str:
    value = _required(mapping, field)
    if not isinstance(value, str) or not value:
        raise ScannerResponseError(f"{prefix} field '{field}' must be a non-empty string")
    return value


def _required_bool(mapping: Mapping[str, object], field: str) -> bool:
    value = _required(mapping, field)
    if not isinstance(value, bool):
        raise ScannerResponseError(f"response field '{field}' must be a boolean")
    return value


def _required_int(
    mapping: Mapping[str, object],
    field: str,
    *,
    minimum: int,
) -> int:
    value = _required(mapping, field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ScannerResponseError(
            f"response field '{field}' must be an integer >= {minimum}"
        )
    return value


def _required_number(
    mapping: Mapping[str, object],
    field: str,
    *,
    minimum: float,
) -> float:
    value = _required(mapping, field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScannerResponseError(f"response field '{field}' must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < minimum:
        raise ScannerResponseError(
            f"response field '{field}' must be a finite number >= {minimum}"
        )
    return parsed


def _optional_str(
    mapping: Mapping[str, object],
    field: str,
    *,
    prefix: str,
) -> str | None:
    value = mapping.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ScannerResponseError(f"{prefix} field '{field}' must be a string or null")
    return value


def _optional_int(
    mapping: Mapping[str, object],
    field: str,
    *,
    prefix: str,
) -> int | None:
    value = mapping.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScannerResponseError(f"{prefix} field '{field}' must be an integer or null")
    return value
