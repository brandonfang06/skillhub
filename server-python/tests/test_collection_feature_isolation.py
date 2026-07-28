import re
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.core.config import get_settings


ROOT = Path(__file__).resolve().parents[2]


def test_collection_features_default_off_without_environment(monkeypatch) -> None:
    monkeypatch.delenv("SKILLHUB_COLLECTIONS_ENABLED", raising=False)
    monkeypatch.delenv("SKILLHUB_GITLAB_IMPORT_ENABLED", raising=False)

    settings = get_settings()

    assert settings.collections_enabled is False
    assert settings.gitlab_import_enabled is False


def test_collection_local_schema_never_uses_upstream_flyway_namespace() -> None:
    upstream_migrations = ROOT / "server-python" / "app" / "db" / "migration"
    local_migrations = ROOT / "server-python" / "app" / "db" / "local_migration"

    assert not list(upstream_migrations.glob("V*__*collection*.sql"))
    assert not list(upstream_migrations.glob("V*__*repository_import*.sql"))

    for path in local_migrations.glob("*__*.sql"):
        if "collection" in path.name or "repository_import" in path.name:
            sql = path.read_text(encoding="utf-8").lower()
            created_tables = re.findall(
                r"create table(?: if not exists)?\s+([a-z0-9_]+)",
                sql,
            )
            assert created_tables
            assert all(name.startswith("local_") for name in created_tables)


def test_collection_program_does_not_reintroduce_java_runtime() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "full-Python backend project" in agents
    assert "Do not reintroduce Java" in agents
    assert "dev-all-hybrid" not in makefile


def test_collection_routes_return_not_found_before_auth_when_feature_is_disabled() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=False)
    app.state.collection_mutation_writer = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("disabled route reached writer")
    )
    client = TestClient(app)

    assert client.get("/api/web/namespaces/opensource/collections").status_code == 404
    assert client.get("/api/web/collections/opensource/superpowers").status_code == 404
    assert client.get("/api/cli/v1/collections/opensource/superpowers/resolve").status_code == 404
    assert client.post("/api/web/namespaces/opensource/collections", json={}).status_code == 404
    assert client.post("/api/web/collections/opensource/superpowers/draft").status_code == 404
    assert client.put("/api/web/collections/opensource/superpowers/draft", json={}).status_code == 404
    assert client.delete("/api/web/collections/opensource/superpowers/draft").status_code == 404
    assert client.post("/api/web/collections/opensource/superpowers/publish", json={}).status_code == 404
    assert client.put("/api/web/collections/opensource/superpowers/status", json={}).status_code == 404


def test_collection_openapi_registers_typed_m1_contracts() -> None:
    schema = create_app().openapi()

    expected_paths = {
        "/api/web/namespaces/{namespace}/collections",
        "/api/web/collections/{namespace}/{collection}",
        "/api/cli/v1/collections/{namespace}/{collection}/resolve",
        "/api/web/collections/{namespace}/{collection}/draft",
        "/api/web/collections/{namespace}/{collection}/publish",
        "/api/web/collections/{namespace}/{collection}/status",
    }

    assert expected_paths <= set(schema["paths"])
    assert {
        "CollectionCreateRequest",
        "CollectionDraftReplaceRequest",
        "CollectionPublishRequest",
        "CollectionResolveResponse",
        "CollectionStatusRequest",
    } <= set(schema["components"]["schemas"])
