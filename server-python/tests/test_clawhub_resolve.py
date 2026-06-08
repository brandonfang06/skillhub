from fastapi.testclient import TestClient

from app.main import create_app


def resolve_reader_response(version: str) -> dict[str, object]:
    return {
        "skillId": 1,
        "namespace": "global",
        "slug": "demo",
        "version": version,
        "versionId": 20,
        "fingerprint": "sha256:abc",
        "matched": None,
        "downloadUrl": f"/api/v1/skills/global/demo/versions/{version}/download",
    }


def test_clawhub_resolve_query_route_returns_plain_response() -> None:
    app = create_app()
    app.state.skill_resolve_reader = lambda namespace, slug, version, tag, hash_value: resolve_reader_response("1.2.0")

    client = TestClient(app)
    response = client.get("/api/v1/resolve", params={"slug": "demo", "version": "latest"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"match", "latestVersion"}
    assert body == {"match": {"version": "1.2.0"}, "latestVersion": {"version": "1.2.0"}}
    assert "code" not in body
    assert "data" not in body


def test_clawhub_resolve_query_route_forwards_legacy_slug_and_hash() -> None:
    seen: list[tuple[str, str, str | None, str | None, str | None]] = []
    app = create_app()
    app.state.clawhub_legacy_slug_reader = lambda slug: ("team-ai", slug)

    def reader(namespace: str, slug: str, version: str | None, tag: str | None, hash_value: str | None):
        seen.append((namespace, slug, version, tag, hash_value))
        return resolve_reader_response("1.2.0")

    app.state.skill_resolve_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/resolve",
        params={"slug": "demo", "version": "latest", "hash": "sha256:abc"},
    )

    assert response.status_code == 200
    assert seen == [("team-ai", "demo", None, "latest", "sha256:abc")]


def test_clawhub_resolve_path_route_parses_canonical_slug() -> None:
    seen: list[tuple[str, str, str | None, str | None, str | None]] = []
    app = create_app()

    def reader(namespace: str, slug: str, version: str | None, tag: str | None, hash_value: str | None):
        seen.append((namespace, slug, version, tag, hash_value))
        return resolve_reader_response(version or "1.2.0")

    app.state.skill_resolve_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/resolve/team-ai--demo", params={"version": "1.2.0", "hash": "ignored"})

    assert response.status_code == 200
    assert seen == [("team-ai", "demo", "1.2.0", None, None)]


def test_clawhub_resolve_path_route_defaults_to_latest_tag() -> None:
    seen: list[tuple[str | None, str | None, str | None]] = []
    app = create_app()

    def reader(namespace: str, slug: str, version: str | None, tag: str | None, hash_value: str | None):
        seen.append((version, tag, hash_value))
        return resolve_reader_response("1.2.0")

    app.state.skill_resolve_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/resolve/demo")

    assert response.status_code == 200
    assert seen == [(None, "latest", None)]


def test_download_remains_unowned_while_v1_skill_detail_is_python_owned() -> None:
    app = create_app()
    app.state.clawhub_skill_detail_reader = lambda namespace, slug: {
        "slug": slug,
        "displayName": "Demo Skill",
        "summary": "Demo summary",
        "namespace": namespace,
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedAt": "2026-06-08T01:02:03Z",
        "updatedAt": "2026-06-08T02:03:04Z",
        "changelog": "Initial release",
    }

    client = TestClient(app)

    assert client.get("/api/v1/download/demo").status_code == 404
    response = client.get("/api/v1/skills/demo")

    assert response.status_code == 200
    assert response.json()["skill"]["slug"] == "demo"
