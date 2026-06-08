from fastapi.testclient import TestClient

from app.main import create_app


def search_response() -> dict[str, object]:
    return {
        "items": [
            {
                "id": 31,
                "slug": "demo-skill",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "visibility": "PUBLIC",
                "status": "ACTIVE",
                "downloadCount": 7,
                "starCount": 3,
                "ratingAvg": 4.5,
                "ratingCount": 4,
                "namespace": "global",
                "updatedAt": "2026-06-07T10:00:00Z",
                "canSubmitPromotion": False,
                "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "ownerPreviewVersion": None,
                "resolutionMode": "PUBLISHED",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def test_skill_search_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_search_reader = lambda **kwargs: search_response()

    client = TestClient(app)
    response = client.get(
        "/api/web/skills",
        headers={"X-Request-Id": "search-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "search-test"
    assert response.json()["code"] == 0
    assert response.json()["requestId"] == "search-test"
    assert response.json()["data"] == search_response()


def test_skill_search_route_forwards_normalized_query_params() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return search_response()

    app.state.skill_search_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills?q= Agent Ops &namespace=global&label=Featured&label=security&sort= downloads &page=2&size=5"
    )

    assert response.status_code == 200
    assert seen == [
        {
            "keyword": " Agent Ops ",
            "namespace": "global",
            "labels": ["featured", "security"],
            "sort": "downloads",
            "page": 2,
            "size": 5,
        }
    ]


def test_skill_search_route_uses_java_style_invalid_page_defaults() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return search_response()

    app.state.skill_search_reader = reader

    client = TestClient(app)
    response = client.get("/api/web/skills?page=-1&size=0")

    assert response.status_code == 200
    assert seen[0]["page"] == 0
    assert seen[0]["size"] == 20


def test_v1_skills_root_uses_clawhub_list_shape() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: search_response()

    client = TestClient(app)
    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    assert set(response.json().keys()) == {"items", "nextCursor"}
    assert "data" not in response.json()
