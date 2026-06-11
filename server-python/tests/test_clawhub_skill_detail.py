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


def test_clawhub_delete_undelete_placeholders_require_auth_and_return_plain_json() -> None:
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

    assert client.delete("/api/v1/skills/demo").status_code == 401

    delete_response = client.delete("/api/v1/skills/demo", headers={"X-Mock-User-Id": "user-1"})
    undelete_response = client.post("/api/v1/skills/team-ai--demo/undelete", headers={"X-Mock-User-Id": "user-1"})

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
    assert undelete_response.status_code == 200
    assert undelete_response.json() == {"ok": True}


def test_clawhub_delete_placeholder_does_not_replace_two_segment_hard_delete(tmp_path) -> None:
    app = create_app()
    seen = []

    async def writer(delete_input):
        seen.append(delete_input)
        return {"skillId": 31, "namespace": delete_input.namespace, "slug": delete_input.slug, "deleted": True}

    app.state.auth_me_reader = lambda user_id: {"userId": user_id, "platformRoles": ["SUPER_ADMIN"]}
    app.state.skill_hard_delete_writer = writer
    app.state.storage_base_path = str(tmp_path)

    client = TestClient(app)
    response = client.delete("/api/v1/skills/global/demo", headers={"X-Mock-User-Id": "admin"})

    assert response.status_code == 200
    assert response.json()["data"]["namespace"] == "global"
    assert response.json()["data"]["slug"] == "demo"
    assert seen[-1].route_scope == "v1"


def test_nested_skillhub_detail_route_keeps_envelope_shape() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug, current_user_id=None: {
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
