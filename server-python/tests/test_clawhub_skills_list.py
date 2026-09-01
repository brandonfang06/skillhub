from fastapi.testclient import TestClient

from app.main import create_app


def portal_search_response() -> dict[str, object]:
    return {
        "items": [
            {
                "id": 31,
                "slug": "demo",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "namespace": "global",
                "downloadCount": 7,
                "starCount": 3,
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "updatedAt": "2026-06-08T01:02:03Z",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 25,
    }


def skill_detail_response() -> dict[str, object]:
    return {
        "slug": "demo",
        "displayName": "Demo Skill",
        "summary": "Demo summary",
        "namespace": "global",
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "createdAt": "2026-06-08T00:01:02Z",
        "publishedAt": "2026-06-08T01:02:03Z",
        "updatedAt": "2026-06-08T02:03:04Z",
        "changelog": "Initial release",
    }


def test_clawhub_skills_list_route_returns_plain_response() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: portal_search_response()

    client = TestClient(app)
    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "nextCursor"}
    assert body["items"][0]["slug"] == "demo"
    assert body["items"][0]["latestVersion"]["version"] == "1.2.0"
    assert "code" not in body
    assert "data" not in body


def test_clawhub_skills_list_route_forwards_query_params() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return portal_search_response()

    app.state.clawhub_skills_list_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills?page=2&limit=5&sort=downloads")

    assert response.status_code == 200
    assert seen == [
        {
            "keyword": "",
            "namespace": None,
            "labels": [],
            "sort": "downloads",
            "page": 2,
            "size": 5,
            "current_user_id": None,
        }
    ]


def test_clawhub_skills_list_route_normalizes_invalid_pagination() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return portal_search_response()

    app.state.clawhub_skills_list_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills?page=-1&limit=0")

    assert response.status_code == 200
    assert seen[0]["page"] == 0
    assert seen[0]["size"] == 25
    assert seen[0]["sort"] == "newest"
    assert seen[0]["current_user_id"] is None


def test_clawhub_skills_list_includes_batched_labels_only_on_request() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: portal_search_response()
    app.state.skill_label_projection_reader = lambda **kwargs: {
        31: [
            {
                "slug": "featured",
                "type": "GENERAL",
                "displayName": "Featured",
            }
        ]
    }
    client = TestClient(app)

    default_response = client.get("/api/v1/skills")
    included_response = client.get("/api/v1/skills?include=labels")

    assert "labels" not in default_response.json()["items"][0]
    assert included_response.json()["items"][0]["labels"] == [
        {"slug": "featured", "type": "GENERAL", "displayName": "Featured"}
    ]


def test_clawhub_skills_list_post_is_owned_by_python_publish_router() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: portal_search_response()

    client = TestClient(app)
    response = client.post("/api/v1/skills")

    assert response.status_code == 422


def test_clawhub_skill_detail_route_stays_owned_by_python() -> None:
    app = create_app()
    app.state.clawhub_skill_detail_reader = lambda namespace, slug: skill_detail_response()

    client = TestClient(app)
    response = client.get("/api/v1/skills/demo")

    assert response.status_code == 200
    assert set(response.json().keys()) == {"skill", "latestVersion", "owner", "moderation"}
