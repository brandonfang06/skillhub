from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from scanner_adapter.client import ScannerClient
from scanner_adapter.config import ScannerAdapterConfig
from scanner_adapter.errors import (
    InputValidationError,
    ScannerHttpError,
    ScannerResponseError,
    ScannerUnavailableError,
)


def test_health_calls_configured_endpoint(
    config: ScannerAdapterConfig,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == "https://scanner.internal/health"
        return httpx.Response(
            200,
            json={
                "status": "healthy",
                "version": "1.2.3",
                "analyzers_available": ["static_analyzer"],
            },
        )

    with ScannerClient(config, transport=httpx.MockTransport(handler)) as client:
        result = client.health()

    assert result["status"] == "healthy"


def test_list_analyzers_calls_configured_endpoint(
    config: ScannerAdapterConfig,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == "https://scanner.internal/analyzers"
        return httpx.Response(
            200,
            json=[
                {"name": "static_analyzer", "available": True},
                {"name": "aidefense_analyzer", "available": True},
            ],
        )

    with ScannerClient(config, transport=httpx.MockTransport(handler)) as client:
        result = client.list_analyzers()

    assert [item["name"] for item in result] == [
        "static_analyzer",
        "aidefense_analyzer",
    ]


def test_list_analyzers_unwraps_official_response_envelope(
    config: ScannerAdapterConfig,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "analyzers": [
                    {"name": "static_analyzer", "available": True},
                    {"name": "aidefense_analyzer", "available": True},
                ]
            },
        )

    with ScannerClient(config, transport=httpx.MockTransport(handler)) as client:
        result = client.list_analyzers()

    assert [item["name"] for item in result] == [
        "static_analyzer",
        "aidefense_analyzer",
    ]


def test_scan_zip_streams_expected_multipart_and_form_fields(
    config: ScannerAdapterConfig,
    skill_zip: Path,
    safe_response: dict[str, object],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert request.method == "POST"
        assert request.url.scheme == "https"
        assert request.url.host == "scanner.internal"
        assert request.url.path == "/scan-upload"
        assert request.url.params["policy"] == "balanced"
        assert request.url.params["use_behavioral"] == "true"
        assert request.url.params["use_llm"] == "false"
        assert request.url.params["llm_provider"] == "openai"
        assert request.url.params["use_aidefense"] == "false"
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert b'name="file"; filename="example.zip"' in body
        assert b"teaching-fixture" in body
        assert b'name="policy"' in body
        assert b"\r\nbalanced\r\n" in body
        assert b'name="use_behavioral"' in body
        assert b"\r\ntrue\r\n" in body
        assert b'name="use_llm"' in body
        assert b'name="llm_provider"' in body
        assert b"\r\nopenai\r\n" in body
        assert b'name="use_aidefense"' in body
        assert request.headers.get("X-AIDefense-Key") is None
        return httpx.Response(200, json=safe_response)

    with ScannerClient(config, transport=httpx.MockTransport(handler)) as client:
        result = client.scan_zip(skill_zip)

    assert result.normalized.analyzers_requested == (
        "static",
        "behavioral",
    )


def test_scan_zip_can_request_llm(
    config: ScannerAdapterConfig,
    skill_zip: Path,
    safe_response: dict[str, object],
) -> None:
    enabled = replace(config, use_llm=True, llm_provider="anthropic")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert request.url.params["use_llm"] == "true"
        assert request.url.params["llm_provider"] == "anthropic"
        assert b'name="use_llm"' in body
        assert b"\r\ntrue\r\n" in body
        assert b'name="llm_provider"' in body
        assert b"\r\nanthropic\r\n" in body
        return httpx.Response(200, json=safe_response)

    with ScannerClient(enabled, transport=httpx.MockTransport(handler)) as client:
        result = client.scan_zip(skill_zip)

    assert result.normalized.analyzers_requested == (
        "static",
        "behavioral",
        "llm",
    )


def test_scan_zip_can_disable_ai_defense_and_behavioral(
    config: ScannerAdapterConfig,
    skill_zip: Path,
    safe_response: dict[str, object],
) -> None:
    disabled = replace(config, use_ai_defense=False, use_behavioral=False)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert body.count(b"\r\nfalse\r\n") == 3
        return httpx.Response(200, json=safe_response)

    with ScannerClient(disabled, transport=httpx.MockTransport(handler)) as client:
        result = client.scan_zip(skill_zip)

    assert result.normalized.analyzers_requested == ("static",)


@pytest.mark.parametrize("case", ["missing", "directory", "non_zip", "oversized"])
def test_scan_zip_validates_input_before_http(
    case: str,
    config: ScannerAdapterConfig,
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    if case == "missing":
        candidate = tmp_path / "missing.zip"
    elif case == "directory":
        candidate = tmp_path / "folder.zip"
        candidate.mkdir()
    elif case == "non_zip":
        candidate = tmp_path / "skill.tar"
        candidate.write_bytes(b"archive")
    else:
        candidate = tmp_path / "large.zip"
        candidate.write_bytes(b"12345")
        config = replace(config, max_zip_bytes=4)

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(InputValidationError),
    ):
        client.scan_zip(candidate)

    assert calls == 0


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("scan timed out"),
    ],
)
def test_request_failure_becomes_scanner_unavailable(
    error: httpx.RequestError,
    config: ScannerAdapterConfig,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        error.request = request
        raise error

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerUnavailableError, match="scanner request failed"),
    ):
        client.health()


def test_non_success_becomes_bounded_scanner_http_error(
    config: ScannerAdapterConfig,
) -> None:
    response_body = "upstream failed\n" + ("x" * 2_000)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text=response_body)

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerHttpError) as captured,
    ):
        client.health()

    message = str(captured.value)
    assert "502" in message
    assert "\n" not in message
    assert len(message) < 600
    assert "x" * 600 not in message


def test_non_json_becomes_scanner_response_error(
    config: ScannerAdapterConfig,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerResponseError, match="valid JSON"),
    ):
        client.health()


def test_malformed_json_becomes_scanner_response_error(
    config: ScannerAdapterConfig,
    skill_zip: Path,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"scan_id": "missing-most-fields"})

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerResponseError, match="findings"),
    ):
        client.scan_zip(skill_zip)


def test_health_rejects_non_object_json(config: ScannerAdapterConfig) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerResponseError, match="JSON object"),
    ):
        client.health()


def test_analyzers_rejects_non_list_json(config: ScannerAdapterConfig) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    with (
        ScannerClient(config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ScannerResponseError, match="JSON list"),
    ):
        client.list_analyzers()


def test_context_manager_closes_owned_http_client(
    config: ScannerAdapterConfig,
) -> None:
    client = ScannerClient(config, transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    owned_http_client = client._http_client

    with client:
        assert owned_http_client.is_closed is False

    assert owned_http_client.is_closed is True


def test_context_manager_does_not_close_injected_http_client(
    config: ScannerAdapterConfig,
) -> None:
    injected = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    with ScannerClient(config, http_client=injected):
        pass

    assert injected.is_closed is False
    injected.close()
