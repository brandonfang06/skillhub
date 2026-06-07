from fastapi.testclient import TestClient

from app.main import create_app


def portal_search_response() -> dict[str, object]:
    return {
        "items": [
            {
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
        "size": 20,
    }


def test_clawhub_search_route_returns_plain_response() -> None:
    app = create_app()
    app.state.clawhub_search_reader = lambda **kwargs: portal_search_response()

    client = TestClient(app)
    response = client.get("/api/v1/search?q=demo")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"results"}
    assert body["results"][0]["slug"] == "demo"
    assert body["results"][0]["version"] == "1.2.0"
    assert "code" not in body
    assert "data" not in body


def test_clawhub_search_route_forwards_query_params_and_sort() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return portal_search_response()

    app.state.clawhub_search_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/search?q=demo&page=2&limit=5")

    assert response.status_code == 200
    assert seen == [
        {
            "keyword": "demo",
            "namespace": None,
            "labels": [],
            "sort": "relevance",
            "page": 2,
            "size": 5,
        }
    ]


def test_clawhub_search_blank_q_uses_newest_sort() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()

    def reader(**kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return portal_search_response()

    app.state.clawhub_search_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/search?q=")

    assert response.status_code == 200
    assert seen[0]["sort"] == "newest"


def test_v1_skills_root_still_remains_unowned_by_python_router() -> None:
    app = create_app()

    client = TestClient(app)
    response = client.get("/api/v1/skills")

    assert response.status_code == 404
