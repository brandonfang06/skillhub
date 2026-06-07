from fastapi.testclient import TestClient

from app.main import create_app


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
    app.state.skill_detail_reader = lambda namespace, slug: detail_response()

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
    app.state.skill_detail_reader = lambda namespace, slug: detail_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo-skill")

    assert response.status_code == 200
    assert response.json()["data"] == detail_response()


def test_skill_detail_route_forwards_params_to_reader() -> None:
    seen: list[tuple[str, str]] = []
    app = create_app()

    def reader(namespace: str, slug: str) -> dict[str, object]:
        seen.append((namespace, slug))
        return detail_response()

    app.state.skill_detail_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/team-a/demo-skill")

    assert response.status_code == 200
    assert seen == [("team-a", "demo-skill")]
