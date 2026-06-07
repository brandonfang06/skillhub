from fastapi.testclient import TestClient

from app.main import create_app


def version_page(page: int, size: int) -> dict[str, object]:
    return {
        "items": [
            {
                "id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "changelog": "latest",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-07T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": page,
        "size": size,
    }


def test_skill_versions_v1_route_returns_page_envelope() -> None:
    app = create_app()
    app.state.skill_versions_reader = lambda namespace, slug, page, size: version_page(page, size)

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions",
        params={"page": 0, "size": 20},
        headers={"X-Request-Id": "versions-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "versions-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "versions-test"
    assert response.json()["data"] == version_page(0, 20)


def test_skill_versions_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_versions_reader = lambda namespace, slug, page, size: version_page(page, size)

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions")

    assert response.status_code == 200
    assert response.json()["data"] == version_page(0, 20)


def test_skill_versions_route_forwards_page_and_size_to_reader() -> None:
    seen: list[tuple[int, int]] = []
    app = create_app()

    def reader(namespace: str, slug: str, page: int, size: int) -> dict[str, object]:
        seen.append((page, size))
        return version_page(page, size)

    app.state.skill_versions_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo/versions", params={"page": 2, "size": 5})

    assert response.status_code == 200
    assert seen == [(2, 5)]
    assert response.json()["data"]["page"] == 2
    assert response.json()["data"]["size"] == 5
