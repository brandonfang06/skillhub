from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.request_id import current_request_id
from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_result import SecurityScanResultInput

DEFAULT_SCANNER_BASE_URL = "http://localhost:8000"
DEFAULT_SCANNER_HEALTH_PATH = "/health"
DEFAULT_SCANNER_SCAN_PATH = "/scan-upload"
DEFAULT_SCANNER_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SCANNER_READ_TIMEOUT_MS = 300000
logger = logging.getLogger("uvicorn.error")


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
    def disabled() -> ScanOptions:
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

    def without_llm(self) -> ScanOptions:
        return replace(self, use_llm=False, enable_meta=False)

    def requested_analyzers(self) -> list[str]:
        analyzers = ["static_analyzer"]
        if self.use_behavioral:
            analyzers.append("behavioral_analyzer")
        if self.use_llm:
            analyzers.append("llm_analyzer")
        if self.enable_meta:
            analyzers.append("meta_analyzer")
        if self.use_aidefense:
            analyzers.append("aidefense_analyzer")
        if self.use_virustotal:
            analyzers.append("virustotal_analyzer")
        if self.use_trigger:
            analyzers.append("trigger_analyzer")
        return analyzers


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
    raw_analyzers = payload.get("analyzers_used")
    analyzers_completed = (
        [str(analyzer) for analyzer in raw_analyzers if str(analyzer)]
        if isinstance(raw_analyzers, list)
        else ["static_analyzer"]
    )
    return SecurityScanResultInput(
        scan_id=str(payload.get("scan_id") or ""),
        verdict=map_verdict(payload.get("is_safe"), payload.get("max_severity")),
        findings_count=int(payload.get("findings_count") or 0),
        max_severity=payload.get("max_severity"),
        findings=[map_finding(finding) for finding in findings if isinstance(finding, dict)],
        scan_duration_seconds=float(payload.get("scan_duration_seconds") or 0.0),
        analyzers_completed=analyzers_completed,
    )


def optional_llm_failure_code(error: Exception) -> str | None:
    if not isinstance(error, httpx.HTTPStatusError):
        return None
    try:
        payload = error.response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("detail"), str):
        return None

    detail = payload["detail"]
    prefix = "Scan failed: "
    if detail.startswith(prefix):
        detail = detail.removeprefix(prefix)
    markers = {
        "SKILLHUB_LLM_ANALYSIS_FAILED:LLM_TIMEOUT": "LLM_TIMEOUT",
        "SKILLHUB_LLM_ANALYSIS_FAILED:LLM_UNAVAILABLE": "LLM_UNAVAILABLE",
    }
    return markers.get(detail)


@dataclass(frozen=True)
class ScannerStageResult:
    result: SecurityScanResultInput
    analyzer_evidence_reported: bool


def validated_scanner_response(response: httpx.Response, options: ScanOptions) -> ScannerStageResult:
    payload = response.json()
    if "analyzers_used" in payload and not isinstance(payload["analyzers_used"], list):
        raise ValueError("Scanner response analyzers_used must be a list")
    result = map_scanner_api_response(payload)
    analyzer_evidence_reported = "analyzers_used" in payload
    if not analyzer_evidence_reported:
        result = replace(result, analyzers_completed=options.requested_analyzers())
        return ScannerStageResult(result, False)
    missing = [
        analyzer
        for analyzer in options.requested_analyzers()
        if analyzer not in result.analyzers_completed
    ]
    if missing:
        raise ValueError(f"Scanner response did not report {', '.join(missing)} completion")
    return ScannerStageResult(result, True)


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
        if not self.options.use_llm:
            stage_result = await self._scan_once(task, skill_path, self.options, stage="complete")
            return replace(stage_result.result, analyzers_requested=self.options.requested_analyzers())

        baseline_options = self.options.without_llm()
        baseline = await self._scan_once(task, skill_path, baseline_options, stage="baseline")
        try:
            enhanced = await self._scan_once(task, skill_path, self.options, stage="enhanced")
        except Exception as exc:
            failure_code = optional_llm_failure_code(exc)
            if failure_code is None:
                raise
            if not baseline.analyzer_evidence_reported or "static_analyzer" not in baseline.result.analyzers_completed:
                raise ValueError("Scanner baseline did not report static_analyzer completion") from None
            return replace(
                baseline.result,
                scan_status="PARTIAL",
                analyzers_requested=self.options.requested_analyzers(),
                analyzer_failures=[{"analyzer": "llm_analyzer", "code": failure_code}],
                failure_code=failure_code,
            )
        return replace(
            enhanced.result,
            analyzers_requested=self.options.requested_analyzers(),
        )

    async def _scan_once(
        self,
        task: SecurityScanTask,
        skill_path: str,
        options: ScanOptions,
        *,
        stage: str,
    ) -> ScannerStageResult:
        if self.mode.lower() == "local":
            return await self.scan_directory(task, skill_path, options=options, stage=stage)
        return await self.scan_upload(task, Path(skill_path), options=options, stage=stage)

    def _log_request(
        self,
        *,
        mode: str,
        task: SecurityScanTask,
        stage: str,
        url: str,
        options: ScanOptions,
    ) -> None:
        logger.info(
            "scan.stage.started task_id=%s version_id=%s scanner_type=%s retry_count=%s stage=%s mode=%s url=%s "
            "use_behavioral=%s use_llm=%s llm_provider=%s "
            "enable_meta=%s use_aidefense=%s use_virustotal=%s use_trigger=%s request_id=%s",
            task.task_id,
            task.version_id,
            task.scanner_type,
            task.retry_count,
            stage,
            mode,
            url,
            options.use_behavioral,
            options.use_llm,
            options.llm_provider,
            options.enable_meta,
            options.use_aidefense,
            options.use_virustotal,
            options.use_trigger,
            current_request_id(),
        )

    @staticmethod
    def _log_response(
        *,
        mode: str,
        task: SecurityScanTask,
        stage: str,
        status_code: int,
        elapsed_ms: int,
    ) -> None:
        logger.info(
            "scan.stage.completed task_id=%s version_id=%s scanner_type=%s retry_count=%s stage=%s mode=%s "
            "status_code=%s request_id=%s elapsed_ms=%s",
            task.task_id,
            task.version_id,
            task.scanner_type,
            task.retry_count,
            stage,
            mode,
            status_code,
            current_request_id(),
            elapsed_ms,
        )

    @staticmethod
    def _log_failure(
        *,
        mode: str,
        task: SecurityScanTask,
        stage: str,
        error: Exception,
        elapsed_ms: int,
    ) -> None:
        status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        logger.warning(
            "scan.stage.failed task_id=%s version_id=%s scanner_type=%s retry_count=%s stage=%s mode=%s "
            "status_code=%s failure_code=%s error_type=%s request_id=%s elapsed_ms=%s",
            task.task_id,
            task.version_id,
            task.scanner_type,
            task.retry_count,
            stage,
            mode,
            status_code,
            optional_llm_failure_code(error) or "SCANNER_ERROR",
            type(error).__name__,
            current_request_id(),
            elapsed_ms,
        )

    async def scan_directory(
        self,
        task: SecurityScanTask,
        skill_directory: str,
        *,
        options: ScanOptions | None = None,
        stage: str = "complete",
    ) -> ScannerStageResult:
        scan_options = options or self.options
        url = f"{self.base_url}/scan"
        self._log_request(mode="local", task=task, stage=stage, url=url, options=scan_options)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(
                    url,
                    json=scan_options.as_json_body(skill_directory),
                    headers=scan_options.as_headers(),
                )
                response.raise_for_status()
                result = validated_scanner_response(response, scan_options)
        except Exception as exc:
            self._log_failure(
                mode="local",
                task=task,
                stage=stage,
                error=exc,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        self._log_response(
            mode="local",
            task=task,
            stage=stage,
            status_code=response.status_code,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
        return result

    async def scan_upload(
        self,
        task: SecurityScanTask,
        skill_package_path: Path,
        *,
        options: ScanOptions | None = None,
        stage: str = "complete",
    ) -> ScannerStageResult:
        scan_options = options or self.options
        url = f"{self.base_url}{self.scan_path}"
        self._log_request(mode="upload", task=task, stage=stage, url=url, options=scan_options)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                with skill_package_path.open("rb") as file_handle:
                    response = await client.post(
                        url,
                        params=scan_options.as_form_fields(),
                        data=scan_options.as_form_fields(),
                        files={"file": (skill_package_path.name, file_handle, "application/zip")},
                        headers=scan_options.as_headers(),
                    )
                response.raise_for_status()
                result = validated_scanner_response(response, scan_options)
        except Exception as exc:
            self._log_failure(
                mode="upload",
                task=task,
                stage=stage,
                error=exc,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        self._log_response(
            mode="upload",
            task=task,
            stage=stage,
            status_code=response.status_code,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
        return result
