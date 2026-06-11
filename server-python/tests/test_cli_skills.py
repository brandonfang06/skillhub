from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.skills import DownloadResult
from app.main import create_app


def search_response() -> dict[str, object]:
    return {
        "items": [
            {
                "slug": "agent-helper",
                "displayName": "Agent Helper",
                "summary": "CLI search summary",
                "namespace": "global",
                "downloadCount": 7,
                "starCount": 3,
                "ratingAvg": 4.5,
                "ratingCount": 2,
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "updatedAt": "2026-06-11T01:02:03Z",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def resolve_response() -> dict[str, object]:
    return {
        "skillId": 10,
        "namespace": "global",
        "slug": "agent-helper",
        "version": "1.2.0",
        "versionId": 41,
        "fingerprint": "abc123",
        "matched": True,
        "downloadUrl": "/api/v1/skills/global/agent-helper/versions/1.2.0/download",
    }


def test_cli_search_returns_java_envelope_and_forwards_query_params() -> None:
    app = create_app()
    seen: list[dict[str, object]] = []

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return search_response()

    app.state.cli_skill_search_reader = reader
    client = TestClient(app)

    response = client.get("/api/cli/v1/skills/search?q=agent&limit=5", headers={"X-Request-Id": "cli-search"})

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "cli-search"
    assert response.json()["data"] == {
        "items": [
            {
                "namespace": "global",
                "slug": "agent-helper",
                "latestVersion": "1.2.0",
                "summary": "CLI search summary",
            }
        ],
        "total": 1,
        "limit": 5,
    }
    assert seen == [
        {
            "keyword": "agent",
            "namespace": None,
            "labels": [],
            "sort": "newest",
            "page": 0,
            "size": 5,
        }
    ]


def test_cli_search_uses_java_default_limit_and_positive_limit_fallback() -> None:
    app = create_app()
    seen: list[dict[str, object]] = []
    app.state.cli_skill_search_reader = lambda **kwargs: seen.append(kwargs) or search_response()
    client = TestClient(app)

    assert client.get("/api/cli/v1/skills/search").status_code == 200
    assert client.get("/api/cli/v1/skills/search?limit=0").status_code == 200

    assert [entry["size"] for entry in seen] == [20, 20]


def test_cli_resolve_returns_java_envelope_shape() -> None:
    app = create_app()
    seen: list[tuple[object, ...]] = []

    def reader(*args: object) -> dict[str, object]:
        seen.append(args)
        return resolve_response()

    app.state.skill_resolve_reader = reader
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/skills/global/agent-helper/resolve?version=1.2.0",
        headers={"X-Request-Id": "cli-resolve"},
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "cli-resolve"
    assert response.json()["data"] == {
        "namespace": "global",
        "slug": "agent-helper",
        "version": "1.2.0",
        "versionId": 41,
        "fingerprint": "abc123",
        "downloadUrl": "/api/v1/skills/global/agent-helper/versions/1.2.0/download",
    }
    assert seen == [("global", "agent-helper", "1.2.0", None, None, None)]


def test_cli_download_routes_stream_existing_python_download_results() -> None:
    app = create_app()
    seen: list[tuple[object, ...]] = []

    async def latest_reader(namespace: str, slug: str, user_id: str | None) -> DownloadResult:
        seen.append(("latest", namespace, slug, user_id))
        return DownloadResult(
            content=b"latest bytes",
            content_type="application/zip",
            filename="latest.zip",
            content_length=12,
        )

    async def version_reader(namespace: str, slug: str, version: str, user_id: str | None) -> DownloadResult:
        seen.append(("version", namespace, slug, version, user_id))
        return DownloadResult(
            content=b"version bytes",
            content_type="application/zip",
            filename="version.zip",
            content_length=13,
        )

    app.state.skill_download_latest_reader = latest_reader
    app.state.skill_download_version_reader = version_reader
    client = TestClient(app)

    latest = client.get("/api/cli/v1/skills/global/agent-helper/download")
    version = client.get(
        "/api/cli/v1/skills/global/agent-helper/versions/1.2.0/download",
        headers={"X-Mock-User-Id": "user-1"},
    )

    assert latest.status_code == 200
    assert latest.content == b"latest bytes"
    assert latest.headers["content-disposition"] == 'attachment; filename="latest.zip"'
    assert version.status_code == 200
    assert version.content == b"version bytes"
    assert version.headers["content-disposition"] == 'attachment; filename="version.zip"'
    assert seen == [
        ("latest", "global", "agent-helper", None),
        ("version", "global", "agent-helper", "1.2.0", "user-1"),
    ]
