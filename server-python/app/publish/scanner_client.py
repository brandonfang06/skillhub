from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_result import SecurityScanResultInput


DEFAULT_SCANNER_BASE_URL = "http://localhost:8000"
DEFAULT_SCANNER_HEALTH_PATH = "/health"
DEFAULT_SCANNER_SCAN_PATH = "/scan-upload"
DEFAULT_SCANNER_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SCANNER_READ_TIMEOUT_MS = 300000


@dataclass(frozen=True)
class ScanOptions:
    use_behavioral: bool
    use_llm: bool
    llm_provider: str
    enable_meta: bool
    use_aidefense: bool
    aidefense_api_key: str
    use_virustotal: bool
    use_trigger: bool

    @staticmethod
    def disabled() -> "ScanOptions":
        return ScanOptions(False, False, "anthropic", False, False, "", False, False)

    def as_form_fields(self) -> dict[str, str]:
        return {
            "use_behavioral": bool_string(self.use_behavioral),
            "use_llm": bool_string(self.use_llm),
            "llm_provider": self.llm_provider,
            "enable_meta": bool_string(self.enable_meta),
            "use_aidefense": bool_string(self.use_aidefense),
            "use_virustotal": bool_string(self.use_virustotal),
            "use_trigger": bool_string(self.use_trigger),
        }

    def as_json_body(self, skill_directory: str) -> dict[str, Any]:
        body: dict[str, Any] = {"skill_directory": skill_directory}
        body.update(
            {
                "use_behavioral": self.use_behavioral,
                "use_llm": self.use_llm,
                "llm_provider": self.llm_provider,
                "enable_meta": self.enable_meta,
                "use_aidefense": self.use_aidefense,
                "use_virustotal": self.use_virustotal,
                "use_trigger": self.use_trigger,
            }
        )
        if self.use_aidefense and self.aidefense_api_key:
            body["aidefense_api_key"] = self.aidefense_api_key
        return body

    def as_headers(self) -> dict[str, str]:
        if self.use_aidefense and self.aidefense_api_key:
            return {"X-AIDefense-Key": self.aidefense_api_key}
        return {}


def bool_string(value: bool) -> str:
    return "true" if value else "false"


def normalize_scanner_base_url(raw_base_url: str) -> str:
    parsed = urlparse(raw_base_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Scanner base URL must use http or https")
    if not parsed.hostname:
        raise ValueError("Scanner base URL must include a host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Scanner base URL must not include user info, query, or fragment")
    return raw_base_url.rstrip("/")


def map_verdict(is_safe: bool | None, max_severity: str | None) -> str:
    if is_safe is True:
        return "SAFE"
    if max_severity is None:
        return "SUSPICIOUS"
    severity = max_severity.upper()
    if severity == "CRITICAL":
        return "BLOCKED"
    if severity == "HIGH":
        return "DANGEROUS"
    return "SUSPICIOUS"


def map_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "ruleId": finding.get("rule_id"),
        "severity": finding.get("severity"),
        "category": finding.get("category"),
        "title": finding.get("title"),
        "message": finding.get("description"),
        "filePath": finding.get("file_path"),
        "lineNumber": finding.get("line_number"),
        "codeSnippet": finding.get("snippet"),
        "remediation": finding.get("remediation"),
        "analyzer": finding.get("analyzer"),
        "metadata": finding.get("metadata") or {},
    }


def map_scanner_api_response(payload: dict[str, Any]) -> SecurityScanResultInput:
    findings = payload.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    return SecurityScanResultInput(
        scan_id=str(payload.get("scan_id") or ""),
        verdict=map_verdict(payload.get("is_safe"), payload.get("max_severity")),
        findings_count=int(payload.get("findings_count") or 0),
        max_severity=payload.get("max_severity"),
        findings=[map_finding(finding) for finding in findings if isinstance(finding, dict)],
        scan_duration_seconds=float(payload.get("scan_duration_seconds") or 0.0),
    )


class ScannerHttpClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_SCANNER_BASE_URL,
        mode: str = "upload",
        scan_path: str = DEFAULT_SCANNER_SCAN_PATH,
        connect_timeout_ms: int = DEFAULT_SCANNER_CONNECT_TIMEOUT_MS,
        read_timeout_ms: int = DEFAULT_SCANNER_READ_TIMEOUT_MS,
        options: ScanOptions | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_scanner_base_url(base_url)
        self.mode = mode
        self.scan_path = scan_path
        self.timeout = httpx.Timeout(
            connect=connect_timeout_ms / 1000,
            read=read_timeout_ms / 1000,
            write=read_timeout_ms / 1000,
            pool=connect_timeout_ms / 1000,
        )
        self.options = options or ScanOptions.disabled()
        self.transport = transport

    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        if self.mode.lower() == "local":
            return await self.scan_directory(skill_path)
        return await self.scan_upload(Path(skill_path))

    async def scan_directory(self, skill_directory: str) -> SecurityScanResultInput:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                f"{self.base_url}/scan",
                json=self.options.as_json_body(skill_directory),
                headers=self.options.as_headers(),
            )
            response.raise_for_status()
            return map_scanner_api_response(response.json())

    async def scan_upload(self, skill_package_path: Path) -> SecurityScanResultInput:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            with skill_package_path.open("rb") as file_handle:
                response = await client.post(
                    f"{self.base_url}{self.scan_path}",
                    data=self.options.as_form_fields(),
                    files={"file": (skill_package_path.name, file_handle, "application/zip")},
                    headers=self.options.as_headers(),
                )
            response.raise_for_status()
            return map_scanner_api_response(response.json())
