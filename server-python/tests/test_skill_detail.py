from fastapi.testclient import TestClient

from app.main import create_app
from app.api import skills as skill_routes


def detail_response() -> dict[str, object]:
    return {
        "id": 31,
        "slug": "demo-skill",
        "displayName": "Demo Skill",
        "ownerId": "owner-1",
        "ownerDisplayName": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "downloadCount": 7,
        "starCount": 3,
        "subscriptionCount": 2,
        "ratingAvg": 4.5,
        "ratingCount": 4,
        "hidden": False,
        "namespace": "global",
        "labels": [],
        "canManageLifecycle": False,
        "platformAdminOverride": False,
        "canSubmitPromotion": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": "PUBLISHED",
    }


def test_skill_detail_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug, current_user_id=None: detail_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo-skill",
        headers={"X-Request-Id": "detail-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "detail-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "detail-test"
    assert response.json()["data"] == detail_response()


def test_skill_detail_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug, current_user_id=None: detail_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo-skill")

    assert response.status_code == 200
    assert response.json()["data"] == detail_response()


def test_skill_detail_route_forwards_params_to_reader() -> None:
    seen: list[tuple[str, str, str | None]] = []
    app = create_app()

    def reader(namespace: str, slug: str, current_user_id: str | None = None) -> dict[str, object]:
        seen.append((namespace, slug, current_user_id))
        return detail_response()

    app.state.skill_detail_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team-a/demo-skill",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("team-a", "demo-skill", "owner-1")]


def test_skill_detail_route_forwards_none_when_mock_user_header_missing_or_blank() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(namespace: str, slug: str, current_user_id: str | None = None) -> dict[str, object]:
        seen.append(current_user_id)
        return detail_response()

    app.state.skill_detail_reader = reader

    client = TestClient(app)
    missing_response = client.get("/api/v1/skills/team-a/demo-skill")
    blank_response = client.get("/api/v1/skills/team-a/demo-skill", headers={"X-Mock-User-Id": "   "})

    assert missing_response.status_code == 200
    assert blank_response.status_code == 200
    assert seen == [None, None]


def test_skill_detail_route_passes_super_admin_read_override_to_repository(monkeypatch) -> None:
    seen: list[tuple[object, str, str, str | None, bool]] = []
    app = create_app()
    app.state.db_engine = object()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SUPER_ADMIN"],
    }

    async def reader(engine, namespace, slug, current_user_id, platform_read_override):
        seen.append((engine, namespace, slug, current_user_id, platform_read_override))
        return detail_response()

    monkeypatch.setattr(skill_routes, "read_skill_detail", reader)
    client = TestClient(app)

    response = client.get(
        "/api/v1/skills/team-a/broken-skill",
        headers={"X-Mock-User-Id": "platform-admin"},
    )

    assert response.status_code == 200
    assert seen[0][1:] == ("team-a", "broken-skill", "platform-admin", True)
