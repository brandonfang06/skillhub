from fastapi.testclient import TestClient

from app.main import create_app


def test_skill_resolve_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_resolve_reader = lambda namespace, slug, version, tag, hash_value, current_user_id: {
        "skillId": 1,
        "namespace": namespace,
        "slug": slug,
        "version": "1.2.0",
        "versionId": 20,
        "fingerprint": "sha256:abc",
        "matched": None,
        "downloadUrl": "/api/v1/skills/global/demo/versions/1.2.0/download",
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/resolve",
        params={"tag": "latest"},
        headers={"X-Request-Id": "resolve-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "resolve-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "resolve-test"
    assert response.json()["data"] == {
        "skillId": 1,
        "namespace": "global",
        "slug": "demo",
        "version": "1.2.0",
        "versionId": 20,
        "fingerprint": "sha256:abc",
        "matched": None,
        "downloadUrl": "/api/v1/skills/global/demo/versions/1.2.0/download",
    }


def test_skill_resolve_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_resolve_reader = lambda namespace, slug, version, tag, hash_value, current_user_id: {
        "skillId": 2,
        "namespace": namespace,
        "slug": slug,
        "version": "1.0.0",
        "versionId": 10,
        "fingerprint": "sha256:def",
        "matched": True,
        "downloadUrl": "/api/v1/skills/global/demo/versions/1.0.0/download",
    }

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/resolve", params={"hash": "sha256:def"})

    assert response.status_code == 200
    assert response.json()["data"]["matched"] is True
    assert response.json()["data"]["version"] == "1.0.0"


def test_skill_resolve_route_forwards_selectors_to_reader() -> None:
    seen: list[tuple[str | None, str | None, str | None, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str | None,
        tag: str | None,
        hash_value: str | None,
        current_user_id: str | None,
    ):
        seen.append((version, tag, hash_value, current_user_id))
        return {
            "skillId": 1,
            "namespace": namespace,
            "slug": slug,
            "version": version or "1.0.0",
            "versionId": 10,
            "fingerprint": "sha256:abc",
            "matched": None,
            "downloadUrl": "/api/v1/skills/global/demo/versions/1.0.0/download",
        }

    app.state.skill_resolve_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/resolve",
        params={"version": "1.0.0", "hash": "sha256:abc"},
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("1.0.0", None, "sha256:abc", "owner-1")]


def test_skill_resolve_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str | None,
        tag: str | None,
        hash_value: str | None,
        current_user_id: str | None,
    ):
        seen.append(current_user_id)
        return {
            "skillId": 1,
            "namespace": namespace,
            "slug": slug,
            "version": "1.0.0",
            "versionId": 10,
            "fingerprint": "sha256:abc",
            "matched": None,
            "downloadUrl": "/api/v1/skills/global/demo/versions/1.0.0/download",
        }

    app.state.skill_resolve_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/resolve",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]
