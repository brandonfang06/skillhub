from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from skillhub_oss_importer.client import AuthorizationError, SkillHubClient, SkillHubError


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
