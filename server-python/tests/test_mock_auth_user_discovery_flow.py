from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.skills import DownloadResult
from app.main import create_app


def principal(user_id: str = "flow-user") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }


def search_response() -> dict[str, object]:
    return {
        "items": [
            {
                "id": 17,
                "slug": "flow-skill",
                "displayName": "Flow Skill",
                "summary": "A skill used by the mock auth discovery flow",
                "visibility": "PUBLIC",
                "status": "ACTIVE",
                "downloadCount": 4,
                "starCount": 1,
                "ratingAvg": 5.0,
                "ratingCount": 1,
                "namespace": "global",
                "updatedAt": "2026-06-20T10:00:00Z",
                "canSubmitPromotion": False,
                "headlineVersion": {"id": 52, "version": "1.0.0", "status": "PUBLISHED"},
                "publishedVersion": {"id": 52, "version": "1.0.0", "status": "PUBLISHED"},
                "ownerPreviewVersion": None,
                "resolutionMode": "PUBLISHED",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def detail_response() -> dict[str, object]:
    return {
        "id": 17,
        "slug": "flow-skill",
        "displayName": "Flow Skill",
        "ownerId": "owner-1",
        "ownerDisplayName": "Owner One",
        "summary": "A skill used by the mock auth discovery flow",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "downloadCount": 4,
        "starCount": 1,
        "subscriptionCount": 0,
        "ratingAvg": 5.0,
        "ratingCount": 1,
        "hidden": False,
        "namespace": "global",
        "labels": [],
        "canManageLifecycle": False,
        "canSubmitPromotion": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": {"id": 52, "version": "1.0.0", "status": "PUBLISHED"},
        "publishedVersion": {"id": 52, "version": "1.0.0", "status": "PUBLISHED"},
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": "PUBLISHED",
    }


def versions_response() -> dict[str, object]:
    return {
        "items": [
            {
                "id": 52,
                "version": "1.0.0",
                "status": "PUBLISHED",
                "changelog": "initial",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-20T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def files_response() -> list[dict[str, object]]:
    return [
        {
            "id": 201,
            "filePath": "SKILL.md",
            "fileSize": 96,
            "contentType": "text/markdown",
            "sha256": "hash-skill-md",
        },
        {
            "id": 202,
            "filePath": "src/main.py",
            "fileSize": 32,
            "contentType": "text/x-python",
            "sha256": "hash-main-py",
        },
    ]


def test_session_user_can_search_view_files_and_download_skill() -> None:
    app = create_app()
    flow: list[tuple[object, ...]] = []
    app.state.local_auth_login = lambda payload: principal(str(payload["username"]))

    def search_reader(**kwargs: object) -> dict[str, object]:
        flow.append(("search", kwargs))
        return search_response()

    def detail_reader(namespace: str, slug: str, current_user_id: str | None) -> dict[str, object]:
        flow.append(("detail", namespace, slug, current_user_id))
        return detail_response()

    def versions_reader(
        namespace: str,
        slug: str,
        page: int,
        size: int,
        current_user_id: str | None,
    ) -> dict[str, object]:
        flow.append(("versions", namespace, slug, page, size, current_user_id))
        return versions_response()

    def files_reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        flow.append(("files", namespace, slug, version, current_user_id))
        return files_response()

    def file_content_reader(
        namespace: str,
        slug: str,
        version: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        flow.append(("file", namespace, slug, version, file_path, current_user_id))
        return b"# Flow Skill\n"

    def download_latest_reader(namespace: str, slug: str, current_user_id: str | None) -> DownloadResult:
        flow.append(("download", namespace, slug, current_user_id))
        return DownloadResult(
            content=b"flow-bundle",
            content_type="application/zip",
            filename="Flow Skill-1.0.0.zip",
        )

    app.state.skill_search_reader = search_reader
    app.state.skill_detail_reader = detail_reader
    app.state.skill_versions_reader = versions_reader
    app.state.skill_version_files_reader = files_reader
    app.state.skill_version_file_content_reader = file_content_reader
    app.state.skill_download_latest_reader = download_latest_reader

    client = TestClient(app)
    login = client.post("/api/v1/auth/local/login", json={"username": "flow-user", "password": "Abcd123!"})
    assert login.status_code == 200

    search = client.get("/api/web/skills?q=flow")
    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["slug"] == "flow-skill"

    detail = client.get("/api/web/skills/global/flow-skill")
    assert detail.status_code == 200
    assert detail.json()["data"]["publishedVersion"]["version"] == "1.0.0"

    versions = client.get("/api/web/skills/global/flow-skill/versions")
    assert versions.status_code == 200
    assert versions.json()["data"]["items"][0]["downloadAvailable"] is True

    files = client.get("/api/web/skills/global/flow-skill/versions/1.0.0/files")
    assert files.status_code == 200
    assert [item["filePath"] for item in files.json()["data"]] == ["SKILL.md", "src/main.py"]

    file_content = client.get(
        "/api/web/skills/global/flow-skill/versions/1.0.0/file",
        params={"path": "SKILL.md"},
    )
    assert file_content.status_code == 200
    assert file_content.content == b"# Flow Skill\n"

    download = client.get("/api/web/skills/global/flow-skill/download")
    assert download.status_code == 200
    assert download.content == b"flow-bundle"
    assert download.headers["content-disposition"] == 'attachment; filename="Flow Skill-1.0.0.zip"'

    assert flow == [
        (
            "search",
            {
                "keyword": "flow",
                "namespace": None,
                "labels": [],
                "sort": "newest",
                "page": 0,
                "size": 20,
                "current_user_id": "flow-user",
            },
        ),
        ("detail", "global", "flow-skill", "flow-user"),
        ("versions", "global", "flow-skill", 0, 20, "flow-user"),
        ("files", "global", "flow-skill", "1.0.0", "flow-user"),
        ("file", "global", "flow-skill", "1.0.0", "SKILL.md", "flow-user"),
        ("download", "global", "flow-skill", "flow-user"),
    ]
