import asyncio

import httpx
import pytest

from app.repository_imports.gitlab_client import (
    GitLabClientConfig,
    GitLabImportClient,
    GitLabImportError,
)


def config(**overrides) -> GitLabClientConfig:
    values = {
        "base_url": "https://gitlab.internal.example",
        "token": "top-secret-token",
        "allowed_groups": ("oss-mirrors",),
        "connect_timeout_ms": 5000,
        "read_timeout_ms": 60000,
        "archive_max_bytes": 1024,
    }
    values.update(overrides)
    return GitLabClientConfig(**values)


def test_client_rejects_non_https_and_disallowed_groups_before_network() -> None:
    with pytest.raises(GitLabImportError, match="baseUrl.httpsRequired"):
        GitLabImportClient(config(base_url="http://gitlab.internal.example"))

    client = GitLabImportClient(config())
    with pytest.raises(GitLabImportError, match="project.notAllowed"):
        asyncio.run(client.preview_source("other/project", "main"))
    with pytest.raises(GitLabImportError, match="project.invalid"):
        asyncio.run(
            client.preview_source(
                "https://evil.example/oss-mirrors/project",
                "main",
            )
        )


def test_client_resolves_ref_and_streams_archive_with_private_token() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/repository/commits/main"):
            return httpx.Response(
                200,
                json={
                    "id": "a" * 40,
                    "web_url": "https://gitlab.internal.example/oss-mirrors/project/-/commit/" + "a" * 40,
                },
            )
        return httpx.Response(200, content=b"zip", headers={"content-length": "3"})

    transport = httpx.MockTransport(handler)
    client = GitLabImportClient(
        config(),
        client=httpx.AsyncClient(transport=transport, follow_redirects=False),
    )

    result = asyncio.run(client.preview_source("oss-mirrors/project", "main"))

    assert result.commit_sha == "a" * 40
    assert result.archive == b"zip"
    assert all(request.headers["private-token"] == "top-secret-token" for request in seen)
    assert all(request.url.host == "gitlab.internal.example" for request in seen)


def test_resolve_ref_does_not_download_an_unchanged_archive() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "c" * 40,
                "web_url": "https://gitlab.internal.example/oss-mirrors/project/-/commit/"
                + "c" * 40,
            },
        )

    client = GitLabImportClient(
        config(),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
        ),
    )

    result = asyncio.run(client.resolve_ref("oss-mirrors/project", "main"))

    assert result.commit_sha == "c" * 40
    assert len(seen) == 1
    assert "/repository/commits/main" in str(seen[0].url)


def test_client_rejects_redirects_and_oversized_chunked_archives() -> None:
    async def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/archive.zip"})

    redirect_client = GitLabImportClient(
        config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)),
    )
    with pytest.raises(GitLabImportError, match="upstream.redirect"):
        asyncio.run(redirect_client.preview_source("oss-mirrors/project", "main"))

    async def oversized_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repository/commits/main"):
            return httpx.Response(200, json={"id": "b" * 40, "web_url": "https://gitlab.internal.example/project"})
        return httpx.Response(200, content=b"12345")

    oversized_client = GitLabImportClient(
        config(archive_max_bytes=4),
        client=httpx.AsyncClient(transport=httpx.MockTransport(oversized_handler)),
    )
    with pytest.raises(GitLabImportError, match="archive.tooLarge"):
        asyncio.run(oversized_client.preview_source("oss-mirrors/project", "main"))


def test_client_redacts_token_and_raw_body_from_errors() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="raw upstream top-secret-token response",
        )

    client = GitLabImportClient(
        config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(GitLabImportError) as captured:
        asyncio.run(client.preview_source("oss-mirrors/project", "main"))

    message = str(captured.value)
    assert "top-secret-token" not in message
    assert "raw upstream" not in message
