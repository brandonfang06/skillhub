from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_client import (
    ScanOptions,
    ScannerHttpClient,
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
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json=api_response(is_safe=True, max_severity=None, findings_count=0, findings=[]))

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
    assert seen["url"] == "http://scanner.test/scan-upload"
    assert "multipart/form-data" in seen["content_type"]
    assert b'name="file"' in seen["body"]
    assert b"zip-bytes" in seen["body"]
    for field, value in {
        "use_behavioral": "true",
        "use_llm": "true",
        "llm_provider": "anthropic",
        "enable_meta": "true",
        "use_aidefense": "true",
        "use_virustotal": "true",
        "use_trigger": "true",
    }.items():
        assert f'name="{field}"'.encode() in seen["body"]
        assert f"\r\n\r\n{value}\r\n".encode() in seen["body"]
    assert request_header(seen, "X-AIDefense-Key") == "aidefense-secret"


@pytest.mark.anyio
async def test_upload_mode_logs_scanner_request_and_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_response(is_safe=True, max_severity=None, findings_count=0, findings=[]))

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

    await client.scan(SecurityScanTask(task_id="task-1", version_id=202), str(bundle))

    assert "Calling scanner API" in caplog.text
    assert "mode=upload" in caplog.text
    assert "version_id=202" in caplog.text
    assert "use_llm=True" in caplog.text
    assert "Scanner API response" in caplog.text
    assert "status_code=200" in caplog.text


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
