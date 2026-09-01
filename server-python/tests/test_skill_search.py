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
            "current_user_id": None,
        }
    ]


def test_skill_search_route_forwards_optional_current_user_id() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return search_response()

    app.state.skill_search_reader = reader

    client = TestClient(app)
    response = client.get("/api/web/skills?q=agent", headers={"X-Mock-User-Id": " user-a "})

    assert response.status_code == 200
    assert seen == [
        {
            "keyword": "agent",
            "namespace": None,
            "labels": [],
            "sort": "newest",
            "page": 0,
            "size": 20,
            "current_user_id": "user-a",
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
    assert seen[0]["current_user_id"] is None


def test_skill_search_route_projects_labels_only_when_requested() -> None:
    app = create_app()
    app.state.skill_search_reader = lambda **kwargs: search_response()
    seen: list[dict[str, object]] = []

    def label_reader(**kwargs: object) -> dict[int, list[dict[str, str]]]:
        seen.append(kwargs)
        return {
            31: [
                {
                    "slug": "featured",
                    "type": "GENERAL",
                    "displayName": "精選",
                }
            ]
        }

    app.state.skill_label_projection_reader = label_reader
    client = TestClient(app)

    response = client.get(
        "/api/web/skills?include=labels,&include=LABELS",
        headers={"Accept-Language": "zh-TW,zh;q=0.9"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["labels"] == [
        {"slug": "featured", "type": "GENERAL", "displayName": "精選"}
    ]
    assert seen == [{"skill_ids": [31], "locale": "zh-TW"}]


def test_skill_search_route_rejects_unsupported_include_before_search() -> None:
    app = create_app()
    search_called = {"value": False}

    def reader(**kwargs: object) -> dict[str, object]:
        search_called["value"] = True
        return search_response()

    app.state.skill_search_reader = reader
    client = TestClient(app)

    response = client.get("/api/web/skills?include=labels,stats")

    assert response.status_code == 400
    assert response.json()["detail"] == "error.request.include.unsupported:stats"
    assert search_called["value"] is False


def test_v1_skills_root_uses_clawhub_list_shape() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: search_response()

    client = TestClient(app)
    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    assert set(response.json().keys()) == {"items", "nextCursor"}
    assert "data" not in response.json()
