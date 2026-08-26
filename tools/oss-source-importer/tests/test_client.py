from __future__ import annotations

import json
import shutil
import ssl
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from tls_runtime_probe import run_probe

from skillhub_oss_importer.client import (
    AuthorizationError,
    SkillHubClient,
    SkillHubError,
    _skillhub_https_context,
)


@contextmanager
def skillhub_server(
    status: int,
    payload: dict[str, object] | bytes,
    headers: dict[str, str] | None = None,
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_GET(self) -> None:
            self._handle()

        def _handle(self) -> None:
            requests.append(
                {
                    "path": self.path,
                    "headers": self.headers,
                    "body": self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                }
            )
            content = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_client_preserves_base_subpath_and_sends_multipart() -> None:
    response = {"code": 0, "data": {"outcome": "IMPORT"}, "requestId": "server-id"}
    with skillhub_server(200, response) as (base_url, requests):
        client = SkillHubClient(f"{base_url}/skillhub", "secret", 10)
        result = client.validate_skill("oss-owner-repo", b"zip", {"sourcePath": "skills/a"})

    assert requests[0]["path"] == "/skillhub/api/cli/v1/source-imports/oss-owner-repo/skills/validate"
    assert requests[0]["headers"]["Authorization"] == "Bearer secret"
    assert b'name="file"' in requests[0]["body"]
    assert json.dumps({"sourcePath": "skills/a"}, separators=(",", ":")).encode() in requests[0]["body"]
    assert result["requestId"] == "server-id"


def test_maps_authorization_failures_without_token_leak() -> None:
    with skillhub_server(403, {"detail": "denied"}) as (base_url, _requests):
        client = SkillHubClient(base_url, "secret", 10)
        with pytest.raises(AuthorizationError) as error:
            client.ensure_namespace("oss-owner-repo", {})
    assert "secret" not in str(error.value)


def test_rejects_non_json_success_response() -> None:
    with skillhub_server(200, b"not-json") as (base_url, _requests):
        client = SkillHubClient(base_url, "secret", 10)
        with pytest.raises(SkillHubError, match="non-JSON"):
            client.ensure_namespace("oss-owner-repo", {})


def test_does_not_follow_redirects_or_forward_the_service_token() -> None:
    success = {"code": 0, "data": {"outcome": "IMPORT"}}
    with skillhub_server(200, success) as (target_url, target_requests):
        redirect = {"code": 302, "detail": "redirect not allowed"}
        with skillhub_server(302, redirect, {"Location": f"{target_url}/capture"}) as (
            source_url,
            source_requests,
        ):
            client = SkillHubClient(source_url, "secret", 10)
            with pytest.raises(SkillHubError, match="302"):
                client.validate_skill("oss-owner-repo", b"zip", {})

    assert len(source_requests) == 1
    assert target_requests == []


def test_default_skillhub_https_context_bypasses_certificate_verification() -> None:
    assert _skillhub_https_context.check_hostname is False
    assert _skillhub_https_context.verify_mode == ssl.CERT_NONE


@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is not installed")
def test_client_calls_skillhub_through_an_untrusted_https_certificate(tmp_path) -> None:
    certificate = tmp_path / "certificate.pem"
    private_key = tmp_path / "private-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=untrusted.internal",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    run_probe(certificate, private_key)
