from fastapi.testclient import TestClient

from app.main import create_app


def portal_detail_response(namespace: str = "global", slug: str = "demo") -> dict[str, object]:
    return {
        "slug": slug,
        "displayName": "Demo Skill",
        "summary": "Demo summary",
        "namespace": namespace,
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedAt": "2026-06-08T01:02:03Z",
        "updatedAt": "2026-06-08T02:03:04Z",
        "changelog": "Initial release",
    }


def test_clawhub_skill_detail_route_returns_plain_response() -> None:
    app = create_app()
    app.state.clawhub_skill_detail_reader = lambda namespace, slug: portal_detail_response(namespace, slug)

    client = TestClient(app)
    response = client.get("/api/v1/skills/demo")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"skill", "latestVersion", "owner", "moderation"}
    assert body["skill"]["slug"] == "demo"
    assert body["latestVersion"]["version"] == "1.2.0"
    assert "code" not in body
    assert "data" not in body


def test_clawhub_skill_detail_route_parses_canonical_slug() -> None:
    seen: list[tuple[str, str]] = []
    app = create_app()

    def reader(namespace: str, slug: str) -> dict[str, object]:
        seen.append((namespace, slug))
        return portal_detail_response(namespace, slug)

    app.state.clawhub_skill_detail_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/team-ai--demo")

    assert response.status_code == 200
    assert seen == [("team-ai", "demo")]
    assert response.json()["skill"]["slug"] == "team-ai--demo"


def test_clawhub_skill_detail_keeps_mutation_paths_unowned() -> None:
    app = create_app()
    app.state.clawhub_skills_list_reader = lambda **kwargs: {
        "items": [],
        "total": 0,
        "page": 0,
        "size": 25,
    }
    app.state.clawhub_skill_detail_reader = lambda namespace, slug: portal_detail_response(namespace, slug)

    client = TestClient(app)

    assert client.get("/api/v1/skills").status_code == 200
    assert client.post("/api/v1/skills/demo/undelete").status_code == 405


def test_nested_skillhub_detail_route_keeps_envelope_shape() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug: {
        "id": 31,
        "slug": slug,
        "displayName": "Demo Skill",
        "namespace": namespace,
    }

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["namespace"] == "global"
