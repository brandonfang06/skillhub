from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app


def configured_app():
    app = create_app()
    app.state.settings = SimpleNamespace(
        playground_token_secret="test-secret",
        playground_token_ttl_seconds=300,
        playground_token_issuer="skillhub-test",
        playground_token_audience="sidecar-test",
        playground_context_max_bytes=120000,
        storage_base_path="C:/tmp/skillhub-storage",
    )
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "platformRoles": ["USER"],
    }
    app.state.playground_version_reader = (
        lambda namespace, slug, version, user_id: {"version": version}
    )
    app.state.playground_context_reader = lambda claims: {
        "skill": {
            "namespace": claims["namespace"],
            "slug": claims["slug"],
            "displayName": "Notes",
            "version": claims["version"],
        },
        "files": [{"path": "SKILL.md", "content": "Summarize"}],
    }
    return app


def test_capability_requires_authentication() -> None:
    response = TestClient(configured_app()).post(
        "/api/web/skills/global/notes/playground-capability",
        json={"version": "1.0.0"},
    )

    assert response.status_code == 401


def test_capability_is_disabled_when_secret_is_empty() -> None:
    app = configured_app()
    app.state.settings.playground_token_secret = ""

    response = TestClient(app).post(
        "/api/web/skills/global/notes/playground-capability",
        headers={"X-Mock-User-Id": "user-1"},
        json={"version": "1.0.0"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "playground_disabled"


def test_capability_and_context_round_trip() -> None:
    client = TestClient(configured_app())
    token_response = client.post(
        "/api/web/skills/global/notes/playground-capability",
        headers={"X-Mock-User-Id": "user-1"},
        json={"version": "1.0.0"},
    )
    token = token_response.json()["token"]

    context_response = client.get(
        "/api/web/playground/context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert token_response.status_code == 200
    assert token_response.json()["expiresAt"] > 0
    assert context_response.status_code == 200
    assert context_response.json()["files"][0]["path"] == "SKILL.md"


def test_context_reader_receives_capability_subject() -> None:
    app = configured_app()
    captured = {}

    def context_reader(claims):
        captured.update(claims)
        return {
            "skill": {
                "namespace": "global",
                "slug": "notes",
                "displayName": "Notes",
                "version": "1.0.0",
            },
            "files": [],
        }

    app.state.playground_context_reader = context_reader
    client = TestClient(app)
    token = client.post(
        "/api/web/skills/global/notes/playground-capability",
        headers={"X-Mock-User-Id": "user-1"},
        json={"version": "1.0.0"},
    ).json()["token"]

    response = client.get(
        "/api/web/playground/context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert captured["sub"] == "user-1"


def test_invalid_capability_never_uses_normal_bearer_auth() -> None:
    app = configured_app()
    app.state.auth_bearer_reader = lambda token: (_ for _ in ()).throw(
        AssertionError("normal bearer auth must not run")
    )

    response = TestClient(app).get(
        "/api/web/playground/context",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_playground_capability"
