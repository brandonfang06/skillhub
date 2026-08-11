from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.request_id import request_id_scope
from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_client import (
    ScannerHttpClient,
    ScanOptions,
    map_scanner_api_response,
    normalize_scanner_base_url,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def api_response(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scan_id": "scan-1",
        "skill_name": "demo",
        "is_safe": False,
        "max_severity": "HIGH",
        "findings_count": 1,
        "findings": [
            {
                "id": "STATIC-001_abc123",
                "rule_id": "STATIC-001",
                "severity": "HIGH",
                "category": "code-execution",
                "title": "Dynamic execution",
                "description": "avoid eval",
                "file_path": "src/main.py",
                "line_number": 12,
                "snippet": "eval(user_input)",
                "remediation": "Use ast.literal_eval instead",
                "analyzer": "static",
                "metadata": {"source": "fixture"},
            }
        ],
        "scan_duration_seconds": 1.25,
        "analyzers_used": ["static_analyzer"],
        "timestamp": "2026-03-22T07:00:00",
    }
    payload.update(overrides)
    return payload


def test_map_scanner_api_response_matches_java_verdict_and_findings() -> None:
    result = map_scanner_api_response(api_response())

    assert result.scan_id == "scan-1"
    assert result.verdict == "DANGEROUS"
    assert result.findings_count == 1
    assert result.max_severity == "HIGH"
    assert result.scan_duration_seconds == 1.25
    assert result.findings == [
        {
            "ruleId": "STATIC-001",
            "severity": "HIGH",
            "category": "code-execution",
            "title": "Dynamic execution",
            "message": "avoid eval",
            "filePath": "src/main.py",
            "lineNumber": 12,
            "codeSnippet": "eval(user_input)",
            "remediation": "Use ast.literal_eval instead",
            "analyzer": "static",
            "metadata": {"source": "fixture"},
        }
    ]


@pytest.mark.parametrize(
    ("is_safe", "max_severity", "expected"),
    [
        (True, "CRITICAL", "SAFE"),
        (False, "CRITICAL", "BLOCKED"),
        (False, "HIGH", "DANGEROUS"),
        (False, "MEDIUM", "SUSPICIOUS"),
        (False, None, "SUSPICIOUS"),
        (False, "LOW", "SUSPICIOUS"),
    ],
)
def test_map_scanner_api_response_matches_java_verdict_matrix(
    is_safe: bool,
    max_severity: str | None,
    expected: str,
) -> None:
    result = map_scanner_api_response(api_response(is_safe=is_safe, max_severity=max_severity, findings=None))

    assert result.verdict == expected
    assert result.findings == []


@pytest.mark.anyio
async def test_upload_mode_posts_multipart_with_java_scan_options(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "url": str(request.url),
                "headers": request.headers,
                "content_type": request.headers["content-type"],
                "body": request.content,
                "query": dict(request.url.params),
            }
        )
        analyzers = ["static_analyzer", "behavioral_analyzer"]
        if request.url.params.get("use_llm") == "true":
            analyzers.append("llm_analyzer")
        if request.url.params.get("enable_meta") == "true":
            analyzers.append("meta_analyzer")
        if request.url.params.get("use_aidefense") == "true":
            analyzers.append("aidefense_analyzer")
        if request.url.params.get("use_virustotal") == "true":
            analyzers.append("virustotal_analyzer")
        if request.url.params.get("use_trigger") == "true":
            analyzers.append("trigger_analyzer")
        return httpx.Response(
            200,
            json=api_response(
                is_safe=True,
                max_severity=None,
                findings_count=0,
                findings=[],
                analyzers_used=analyzers,
            ),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test/",
        mode="upload",
        options=ScanOptions(
            use_behavioral=True,
            use_llm=True,
            llm_provider="anthropic",
            enable_meta=True,
            use_aidefense=True,
            aidefense_api_key="aidefense-secret",
            use_virustotal=True,
            use_trigger=True,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = await client.scan(SecurityScanTask(task_id="task-1", version_id=202), str(bundle))

    assert result.verdict == "SAFE"
    assert result.scan_status == "COMPLETE"
    assert result.analyzers_completed == [
        "static_analyzer",
        "behavioral_analyzer",
        "llm_analyzer",
        "meta_analyzer",
        "aidefense_analyzer",
        "virustotal_analyzer",
        "trigger_analyzer",
    ]
    assert len(seen) == 2
    assert seen[0]["query"]["use_llm"] == "false"
    assert seen[0]["query"]["enable_meta"] == "false"
    assert seen[1]["query"]["use_llm"] == "true"
    assert seen[1]["query"]["enable_meta"] == "true"
    assert seen[1]["url"].startswith("http://scanner.test/scan-upload?")
    assert "multipart/form-data" in seen[1]["content_type"]
    assert b'name="file"' in seen[1]["body"]
    assert b"zip-bytes" in seen[1]["body"]
    for field, value in {
        "use_behavioral": "true",
        "use_llm": "true",
        "llm_provider": "anthropic",
        "enable_meta": "true",
        "use_aidefense": "true",
        "use_virustotal": "true",
        "use_trigger": "true",
    }.items():
        assert seen[1]["query"][field] == value
        assert f'name="{field}"'.encode() in seen[1]["body"]
        assert f"\r\n\r\n{value}\r\n".encode() in seen[1]["body"]
    assert request_header(seen[1], "X-AIDefense-Key") == "aidefense-secret"


@pytest.mark.anyio
async def test_reported_llm_success_without_llm_analyzer_is_not_complete(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        analyzers = ["static_analyzer"]
        return httpx.Response(
            200,
            json=api_response(
                is_safe=True,
                max_severity=None,
                findings_count=0,
                findings=[],
                analyzers_used=analyzers,
            ),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(False, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="did not report llm_analyzer completion"):
        await client.scan(SecurityScanTask(task_id="task-missing-llm", version_id=205), str(bundle))


@pytest.mark.anyio
async def test_reported_response_requires_every_requested_analyzer(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=api_response(
                is_safe=True,
                max_severity=None,
                findings_count=0,
                findings=[],
                analyzers_used=["static_analyzer"],
            ),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(True, False, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="behavioral_analyzer"):
        await client.scan(SecurityScanTask(task_id="task-missing-behavioral", version_id=208), str(bundle))


@pytest.mark.anyio
async def test_present_non_list_analyzer_evidence_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response(analyzers_used="static_analyzer"))

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="analyzers_used must be a list"):
        await client.scan(SecurityScanTask(task_id="task-malformed-analyzers", version_id=209), str(bundle))


@pytest.mark.anyio
async def test_legacy_llm_success_without_analyzer_evidence_remains_compatible(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = api_response(is_safe=True, max_severity=None, findings_count=0, findings=[])
        payload.pop("analyzers_used")
        return httpx.Response(200, json=payload)

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(False, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    result = await client.scan(SecurityScanTask(task_id="task-legacy-llm", version_id=206), str(bundle))

    assert result.scan_status == "COMPLETE"
    assert result.analyzers_requested == ["static_analyzer", "llm_analyzer"]
    assert result.analyzers_completed == ["static_analyzer", "llm_analyzer"]


@pytest.mark.anyio
async def test_upload_mode_logs_scanner_request_and_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        analyzers = ["static_analyzer", "behavioral_analyzer"]
        if request.url.params.get("use_llm") == "true":
            analyzers.append("llm_analyzer")
        return httpx.Response(
            200,
            json=api_response(
                is_safe=True,
                max_severity=None,
                findings_count=0,
                findings=[],
                analyzers_used=analyzers,
            ),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        mode="upload",
        options=ScanOptions(
            use_behavioral=True,
            use_llm=True,
            llm_provider="anthropic",
            enable_meta=False,
            use_aidefense=False,
            aidefense_api_key="",
            use_virustotal=False,
            use_trigger=False,
        ),
        transport=httpx.MockTransport(handler),
    )
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    with request_id_scope("scanner-log-request"):
        await client.scan(SecurityScanTask(task_id="task-1", version_id=202), str(bundle))

    assert "scan.stage.started" in caplog.text
    assert "task_id=task-1" in caplog.text
    assert "mode=upload" in caplog.text
    assert "version_id=202" in caplog.text
    assert "use_llm=True" in caplog.text
    assert "stage=baseline" in caplog.text
    assert "stage=enhanced" in caplog.text
    assert "scan.stage.completed" in caplog.text
    assert "status_code=200" in caplog.text
    assert "request_id=scanner-log-request" in caplog.text
    assert "elapsed_ms=" in caplog.text


@pytest.mark.anyio
async def test_generic_enhanced_read_timeout_is_not_overridable(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("use_llm") == "true":
            raise httpx.ReadTimeout("provider took too long", request=request)
        return httpx.Response(
            200,
            json=api_response(
                is_safe=True,
                max_severity=None,
                findings_count=0,
                findings=[],
                analyzers_used=["static_analyzer", "behavioral_analyzer"],
            ),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        mode="upload",
        options=ScanOptions(True, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.ReadTimeout):
        await client.scan(SecurityScanTask(task_id="task-timeout", version_id=203), str(bundle))

    assert len(requests) == 2


@pytest.mark.anyio
async def test_exact_scanner_unavailable_marker_preserves_baseline_as_partial(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("use_llm") == "true":
            return httpx.Response(
                500,
                json={"detail": "Scan failed: SKILLHUB_LLM_ANALYSIS_FAILED:LLM_UNAVAILABLE"},
            )
        return httpx.Response(
            200,
            json=api_response(is_safe=True, findings_count=0, findings=[], analyzers_used=["static_analyzer"]),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(False, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    result = await client.scan(SecurityScanTask(task_id="task-unavailable", version_id=204), str(bundle))

    assert result.scan_status == "PARTIAL"
    assert result.failure_code == "LLM_UNAVAILABLE"


@pytest.mark.anyio
async def test_exact_llm_marker_requires_reported_static_baseline_completion(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("use_llm") == "true":
            return httpx.Response(
                500,
                json={"detail": "Scan failed: SKILLHUB_LLM_ANALYSIS_FAILED:LLM_TIMEOUT"},
            )
        return httpx.Response(
            200,
            json=api_response(is_safe=True, findings_count=0, findings=[], analyzers_used=[]),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(False, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="static_analyzer completion"):
        await client.scan(SecurityScanTask(task_id="task-missing-static", version_id=207), str(bundle))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="service unavailable"),
        httpx.Response(500, json={"detail": "SKILLHUB_LLM_ANALYSIS_FAILED:LLM_ERROR"}),
        httpx.Response(500, json={"detail": "Scan failed: SKILLHUB_LLM_ANALYSIS_FAILED:LLM_TIMEOUT extra"}),
    ],
)
async def test_generic_enhanced_failure_is_not_overridable(tmp_path: Path, response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("use_llm") == "true":
            return response
        return httpx.Response(
            200,
            json=api_response(is_safe=True, findings_count=0, findings=[], analyzers_used=["static_analyzer"]),
        )

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"zip-bytes")
    client = ScannerHttpClient(
        base_url="http://scanner.test",
        options=ScanOptions(False, True, "openai", False, False, "", False, False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.scan(SecurityScanTask(task_id="task-failed", version_id=205), str(bundle))


def request_header(seen: dict[str, Any], name: str) -> str | None:
    return seen["headers"].get(name)


@pytest.mark.anyio
async def test_local_mode_posts_directory_json_with_java_scan_options() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.content
        return httpx.Response(200, json=api_response(is_safe=True, max_severity=None, findings_count=0, findings=[]))

    client = ScannerHttpClient(
        base_url="http://scanner.test",
        mode="local",
        transport=httpx.MockTransport(handler),
    )

    result = await client.scan(SecurityScanTask(task_id="task-1", version_id=202), "/tmp/skill")

    assert result.verdict == "SAFE"
    assert seen["url"] == "http://scanner.test/scan"
    assert seen["json"] == (
        b'{"skill_directory":"/tmp/skill","use_behavioral":false,"use_llm":false,'
        b'"llm_provider":"anthropic","enable_meta":false,"use_aidefense":false,'
        b'"use_virustotal":false,"use_trigger":false}'
    )


def test_normalize_scanner_base_url_rejects_java_invalid_shapes() -> None:
    assert normalize_scanner_base_url("http://scanner.test/") == "http://scanner.test"

    for value in [
        "file:///tmp/scanner",
        "http://user:secret@scanner.test",
        "http://scanner.test?x=1",
        "http://scanner.test#frag",
    ]:
        with pytest.raises(ValueError):
            normalize_scanner_base_url(value)


def test_scan_options_disabled_matches_java_defaults() -> None:
    assert ScanOptions.disabled().as_form_fields() == {
        "use_behavioral": "false",
        "use_llm": "false",
        "llm_provider": "anthropic",
        "enable_meta": "false",
        "use_aidefense": "false",
        "use_virustotal": "false",
        "use_trigger": "false",
    }
