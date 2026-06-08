from fastapi.testclient import TestClient

from app.main import create_app


def detail_response(version: str = "1.2.0") -> dict[str, object]:
    return {
        "id": 20,
        "version": version,
        "status": "PUBLISHED",
        "changelog": "latest",
        "fileCount": 2,
        "totalSize": 128,
        "publishedAt": "2026-06-07T10:00:00Z",
        "parsedMetadataJson": "{\"name\":\"demo\"}",
        "manifestJson": "[{\"path\":\"SKILL.md\"}]",
    }


def test_skill_version_detail_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_detail_reader = (
        lambda namespace, slug, version, current_user_id: detail_response(version)
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0",
        headers={"X-Request-Id": "version-detail-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "version-detail-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "version-detail-test"
    assert response.json()["data"] == detail_response()


def test_skill_version_detail_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_version_detail_reader = (
        lambda namespace, slug, version, current_user_id: detail_response(version)
    )

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions/1.2.0")

    assert response.status_code == 200
    assert response.json()["data"] == detail_response()


def test_skill_version_detail_route_forwards_version_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append((namespace, slug, version, current_user_id))
        return detail_response(version)

    app.state.skill_version_detail_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.0.0",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "1.0.0", "owner-1")]
    assert response.json()["data"]["version"] == "1.0.0"


def test_skill_version_detail_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return detail_response(version)

    app.state.skill_version_detail_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/1.0.0",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]
