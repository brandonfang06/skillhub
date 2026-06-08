from fastapi.testclient import TestClient
from app.main import create_app

def files_response() -> list[dict[str, object]]:
    return [
        {
            "id": 21,
            "filePath": "SKILL.md",
            "fileSize": 1024,
            "contentType": "text/markdown",
            "sha256": "hash-skill-md"
        },
        {
            "id": 22,
            "filePath": "app.py",
            "fileSize": 2048,
            "contentType": "text/x-python",
            "sha256": "hash-app-py"
        }
    ]

def test_skill_version_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_files_reader = lambda namespace, slug, version, current_user_id: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0/files",
        headers={"X-Request-Id": "files-version-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-version-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-version-test"
    assert response.json()["data"] == files_response()

def test_skill_version_files_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_version_files_reader = lambda namespace, slug, version, current_user_id: files_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions/1.2.0/files")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == files_response()

def test_skill_tag_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_tag_files_reader = lambda namespace, slug, tag, current_user_id: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/latest/files",
        headers={"X-Request-Id": "files-tag-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-tag-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-tag-test"
    assert response.json()["data"] == files_response()

def test_skill_tag_files_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_tag_files_reader = lambda namespace, slug, tag, current_user_id: files_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/tags/latest/files")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == files_response()

def test_skill_version_files_route_forwards_params_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append((namespace, slug, version, current_user_id))
        return files_response()

    app.state.skill_version_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.0.0/files",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "1.0.0", "owner-1")]

def test_skill_version_files_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append(current_user_id)
        return files_response()

    app.state.skill_version_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/1.0.0/files",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]

def test_skill_tag_files_route_forwards_params_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append((namespace, slug, tag, current_user_id))
        return files_response()

    app.state.skill_tag_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/stable/files",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "stable", "owner-1")]

def test_skill_tag_files_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append(current_user_id)
        return files_response()

    app.state.skill_tag_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/tags/stable/files",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]
