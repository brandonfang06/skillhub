"""Stable result models exposed by the teaching adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedFinding:
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    file_path: str | None
    line_number: int | None
    remediation: str | None
    analyzer: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "remediation": self.remediation,
            "analyzer": self.analyzer,
        }


@dataclass(frozen=True, slots=True)
class NormalizedScan:
    scan_id: str
    skill_name: str
    is_safe: bool
    max_severity: str
    findings_count: int
    scan_duration_seconds: float
    analyzers_requested: tuple[str, ...]
    findings: tuple[NormalizedFinding, ...]
    schema_version: str = "1"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scan_id": self.scan_id,
            "skill_name": self.skill_name,
            "is_safe": self.is_safe,
            "max_severity": self.max_severity,
            "findings_count": self.findings_count,
            "scan_duration_seconds": self.scan_duration_seconds,
            "analyzers_requested": list(self.analyzers_requested),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class ScanResult:
    normalized: NormalizedScan
    raw_response: Mapping[str, object]
