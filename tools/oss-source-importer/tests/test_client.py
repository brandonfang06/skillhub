import json

import httpx
import pytest

from skillhub_oss_importer.client import AuthorizationError, SkillHubClient


def test_client_preserves_base_subpath_and_sends_multipart() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"outcome": "IMPORT"}, "requestId": "server-id"})

    client = SkillHubClient(
        "https://skillhub.example/skillhub",
        "secret",
        10,
        transport=httpx.MockTransport(handler),
    )
    client.validate_skill("oss-owner-repo", b"zip", {"sourcePath": "skills/a"})

    assert seen[0].url.path == "/skillhub/api/cli/v1/source-imports/oss-owner-repo/skills/validate"
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert b'name="file"' in seen[0].content
    assert json.dumps({"sourcePath": "skills/a"}, separators=(",", ":")).encode() in seen[0].content


def test_maps_authorization_failures_without_token_leak() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(403, json={"detail": "denied"}))
    client = SkillHubClient("https://skillhub.example", "secret", 10, transport=transport)
    with pytest.raises(AuthorizationError) as error:
        client.ensure_namespace("oss-owner-repo", {})
    assert "secret" not in str(error.value)
