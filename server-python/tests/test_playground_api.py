from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import playground as playground_api
from app.main import create_app
from app.skills.read_files import SkillResolveError


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


def test_production_context_path_revalidates_access_without_download_side_effects(
    monkeypatch,
) -> None:
    app = configured_app()
    delattr(app.state, "playground_context_reader")
    app.state.db_engine = object()
    app.state.skill_download_reader = lambda *args: (_ for _ in ()).throw(
        AssertionError("download reader must not run")
    )
    captured: list[tuple[str, str]] = []

    async def read_detail(engine, namespace, slug, current_user_id):
        assert engine is app.state.db_engine
        assert current_user_id == "user-1"
        captured.append(("detail", current_user_id))
        return {"displayName": "Notes"}

    async def read_files(engine, namespace, slug, version, current_user_id):
        assert engine is app.state.db_engine
        assert current_user_id == "user-1"
        captured.append(("files", current_user_id))
        return [{"filePath": "SKILL.md", "fileSize": 9}]

    async def read_content(
        engine,
        storage_base_path,
        namespace,
        slug,
        version,
        file_path,
        current_user_id,
    ):
        assert engine is app.state.db_engine
        assert current_user_id == "user-1"
        assert file_path == "SKILL.md"
        captured.append(("content", current_user_id))
        return b"Summarize"

    monkeypatch.setattr(playground_api, "read_skill_detail", read_detail)
    monkeypatch.setattr(playground_api, "read_skill_version_files", read_files)
    monkeypatch.setattr(
        playground_api,
        "read_skill_version_file_content",
        read_content,
    )
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
    assert response.json()["files"] == [
        {"path": "SKILL.md", "content": "Summarize"}
    ]
    assert captured == [
        ("detail", "user-1"),
        ("files", "user-1"),
        ("content", "user-1"),
    ]


def test_production_context_path_rejects_access_revoked_after_token_issuance(
    monkeypatch,
) -> None:
    app = configured_app()
    delattr(app.state, "playground_context_reader")
    app.state.db_engine = object()

    async def reject_detail(engine, namespace, slug, current_user_id):
        assert current_user_id == "user-1"
        raise SkillResolveError("error.skill.forbidden", status_code=403)

    monkeypatch.setattr(playground_api, "read_skill_detail", reject_detail)
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

    assert response.status_code == 403
    assert response.json()["detail"] == "error.skill.forbidden"
