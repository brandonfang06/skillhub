import inspect
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

from fastapi.testclient import TestClient

import pytest

from app.api.skills import (
    DownloadResult,
    SkillResolveError,
    assert_download_access,
    assert_installable_download_access,
    build_download_filename,
    build_download_response,
    read_skill_download_latest,
    read_skill_download_tag,
    read_skill_download_version,
    read_bundle_or_build_fallback_zip,
    sanitize_download_filename,
)
from app.main import create_app
from app.skills import read_files as read_files_module


def session_principal(user_id: str = "local-user") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }


def test_clawhub_download_path_latest_redirects_to_portal_latest() -> None:
    app = create_app()

    client = TestClient(app, follow_redirects=False)
    response = client.get("/api/v1/download/demo")

    assert response.status_code == 302
    assert response.headers["location"] == "/api/v1/skills/global/demo/download"


def test_clawhub_download_path_explicit_version_redirects_to_portal_version() -> None:
    app = create_app()

    client = TestClient(app, follow_redirects=False)
    response = client.get("/api/v1/download/team-ai--demo", params={"version": "1.2.0"})

    assert response.status_code == 302
    assert response.headers["location"] == "/api/v1/skills/team-ai/demo/versions/1.2.0/download"


def test_clawhub_download_query_redirects_through_legacy_coordinate_resolution() -> None:
    app = create_app()
    app.state.clawhub_legacy_slug_reader = lambda slug: ("team-ai", slug)

    client = TestClient(app, follow_redirects=False)
    response = client.get("/api/v1/download", params={"slug": "demo", "version": "latest"})

    assert response.status_code == 302
    assert response.headers["location"] == "/api/v1/skills/team-ai/demo/download"


def test_clawhub_download_query_forwards_current_user_to_coordinate_reader() -> None:
    seen: list[tuple[str, str | None]] = []
    app = create_app()

    def reader(slug: str, current_user_id: str | None) -> tuple[str, str]:
        seen.append((slug, current_user_id))
        return "team-ai", slug

    app.state.clawhub_download_coordinate_reader = reader

    client = TestClient(app, follow_redirects=False)
    response = client.get(
        "/api/v1/download",
        params={"slug": "demo", "version": "1.0.0"},
        headers={"X-Mock-User-Id": " local-user "},
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/api/v1/skills/team-ai/demo/versions/1.0.0/download"
    assert seen == [("demo", "local-user")]


def test_sanitize_download_filename_matches_java_safe_name_style() -> None:
    assert sanitize_download_filename(" Demo / Skill ?.zip ") == "Demo - Skill -.zip"
    assert sanitize_download_filename("   ") == "skill"


def test_build_download_filename_prefers_display_name() -> None:
    assert build_download_filename("Demo Skill", "demo", "1.2.0") == "Demo Skill-1.2.0.zip"


def test_build_download_filename_falls_back_to_slug() -> None:
    assert build_download_filename(None, "demo-skill", "1.0.0") == "demo-skill-1.0.0.zip"


def test_read_bundle_or_build_fallback_zip_reads_bundle_exact_bytes(tmp_path) -> None:
    bundle = tmp_path / "packages" / "1" / "20" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"bundle-bytes")

    result = read_bundle_or_build_fallback_zip(
        str(tmp_path),
        {
            "skill_id": 1,
            "version_id": 20,
            "version": "1.0.0",
            "display_name": "Demo",
            "slug": "demo",
            "content_type": "application/x-zip-compressed",
            "content_length": 12,
        },
        [],
    )

    assert result.content == b"bundle-bytes"
    assert result.content_type == "application/x-zip-compressed"
    assert result.content_length == 12
    assert result.filename == "Demo-1.0.0.zip"


def test_read_bundle_or_build_fallback_zip_reads_bundle_from_object_storage(
    tmp_path,
    monkeypatch,
    fake_object_storage_factory,
) -> None:
    storage = fake_object_storage_factory({"packages/1/20/bundle.zip": b"object-storage-bundle"})
    monkeypatch.setattr(read_files_module, "object_storage_for_base_path", lambda storage_base_path: storage)

    result = read_bundle_or_build_fallback_zip(
        str(tmp_path / "missing-local-storage"),
        {
            "skill_id": 1,
            "version_id": 20,
            "version": "1.0.0",
            "display_name": "Demo",
            "slug": "demo",
            "content_type": "application/zip",
            "content_length": None,
        },
        [],
    )

    assert result.content == b"object-storage-bundle"
    assert result.content_type == "application/zip"
    assert result.content_length == len(b"object-storage-bundle")
    assert not (tmp_path / "missing-local-storage").exists()


def test_read_bundle_or_build_fallback_zip_builds_sorted_zip_from_files(tmp_path) -> None:
    first = tmp_path / "objects" / "a.md"
    second = tmp_path / "objects" / "b.md"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    result = read_bundle_or_build_fallback_zip(
        str(tmp_path),
        {
            "skill_id": 1,
            "version_id": 20,
            "version": "1.0.0",
            "display_name": "Demo",
            "slug": "demo",
            "content_type": None,
            "content_length": None,
        },
        [
            {"file_path": "b.md", "storage_key": "objects/b.md"},
            {"file_path": "a.md", "storage_key": "objects/a.md"},
        ],
    )

    assert result.content_type == "application/zip"
    assert result.content_length == len(result.content)
    with ZipFile(result.as_bytes_io()) as zip_file:
        assert zip_file.namelist() == ["a.md", "b.md"]
        assert zip_file.read("a.md") == b"a"
        assert zip_file.read("b.md") == b"b"


def test_read_bundle_or_build_fallback_zip_raises_when_no_bundle_or_files(tmp_path) -> None:
    with pytest.raises(SkillResolveError, match="error.skill.bundle.notFound"):
        read_bundle_or_build_fallback_zip(
            str(tmp_path),
            {
                "skill_id": 1,
                "version_id": 20,
                "version": "1.0.0",
                "display_name": "Demo",
                "slug": "demo",
                "content_type": None,
                "content_length": None,
            },
            [],
        )


def test_assert_download_access_rejects_unsupported_status() -> None:
    with pytest.raises(SkillResolveError, match="error.skill.version.notDownloadable"):
        assert_download_access({"status": "YANKED"}, can_manage=True)


def test_assert_download_access_allows_published_without_manager() -> None:
    assert_download_access({"status": "PUBLISHED"}, can_manage=False)


def test_assert_download_access_allows_java_public_preview_statuses() -> None:
    assert_download_access({"status": "PENDING_REVIEW"}, can_manage=False)
    assert_download_access({"status": "UPLOADED"}, can_manage=False)


def test_assert_download_access_allows_uploaded_or_pending_for_manager() -> None:
    assert_download_access({"status": "UPLOADED"}, can_manage=True)
    assert_download_access({"status": "PENDING_REVIEW"}, can_manage=True)


def test_assert_installable_download_access_requires_ready_published_not_yanked() -> None:
    assert_installable_download_access({"status": "PUBLISHED", "download_ready": True, "yanked_at": None})
    with pytest.raises(SkillResolveError, match="error.skill.version.notDownloadable"):
        assert_installable_download_access({"status": "PUBLISHED", "download_ready": False, "yanked_at": None})
    with pytest.raises(SkillResolveError, match="error.skill.version.notDownloadable"):
        assert_installable_download_access({"status": "PUBLISHED", "download_ready": True, "yanked_at": "2026-06-20"})
    with pytest.raises(SkillResolveError, match="error.skill.version.notDownloadable"):
        assert_installable_download_access({"status": "PENDING_REVIEW", "download_ready": True, "yanked_at": None})


def test_portal_latest_download_route_streams_bytes_and_headers() -> None:
    app = create_app()
    app.state.skill_download_latest_reader = lambda namespace, slug, current_user_id: DownloadResult(
        content=b"bundle",
        content_type="application/zip",
        filename="Demo-1.0.0.zip",
    )

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo/download")

    assert response.status_code == 200
    assert response.content == b"bundle"
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-length"] == "6"
    assert response.headers["content-disposition"] == 'attachment; filename="Demo-1.0.0.zip"'


def test_web_latest_download_alias_streams_bytes_and_headers() -> None:
    app = create_app()
    app.state.skill_download_latest_reader = lambda namespace, slug, current_user_id: DownloadResult(
        content=b"web-bundle",
        content_type="application/zip",
        filename="Demo-1.0.0.zip",
    )

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/download")

    assert response.status_code == 200
    assert response.content == b"web-bundle"
    assert response.headers["content-disposition"] == 'attachment; filename="Demo-1.0.0.zip"'


def test_portal_version_download_route_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(namespace: str, slug: str, version: str, current_user_id: str | None) -> DownloadResult:
        seen.append((namespace, slug, version, current_user_id))
        return DownloadResult(content=b"version", content_type="application/zip", filename="Demo-1.1.0.zip")

    app.state.skill_download_version_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team-ai/demo/versions/1.1.0/download",
        headers={"X-Mock-User-Id": " local-user "},
    )

    assert response.status_code == 200
    assert response.content == b"version"
    assert seen == [("team-ai", "demo", "1.1.0", "local-user")]


def test_web_version_download_alias_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(namespace: str, slug: str, version: str, current_user_id: str | None) -> DownloadResult:
        seen.append((namespace, slug, version, current_user_id))
        return DownloadResult(content=b"web-version", content_type="application/zip", filename="Demo-1.1.0.zip")

    app.state.skill_download_version_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/team-ai/demo/versions/1.1.0/download",
        headers={"X-Mock-User-Id": " local-user "},
    )

    assert response.status_code == 200
    assert response.content == b"web-version"
    assert seen == [("team-ai", "demo", "1.1.0", "local-user")]


def test_version_download_route_uses_session_principal() -> None:
    seen: list[str | None] = []
    app = create_app()
    app.state.local_auth_login = lambda payload: session_principal()

    def reader(namespace: str, slug: str, version: str, current_user_id: str | None) -> DownloadResult:
        seen.append(current_user_id)
        return DownloadResult(content=b"version", content_type="application/zip", filename="Demo-1.1.0.zip")

    app.state.skill_download_version_reader = reader

    client = TestClient(app)
    client.post("/api/v1/auth/local/login", json={"username": "local-user", "password": "Abcd123!"})
    response = client.get("/api/web/skills/team-ai/demo/versions/1.1.0/download")

    assert response.status_code == 200
    assert seen == ["local-user"]


def test_portal_tag_download_route_streams_bytes() -> None:
    app = create_app()
    app.state.skill_download_tag_reader = lambda namespace, slug, tag, current_user_id: DownloadResult(
        content=b"tag",
        content_type="application/zip",
        filename="Demo-1.0.0.zip",
    )

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo/tags/stable/download")

    assert response.status_code == 200
    assert response.content == b"tag"


def test_web_tag_download_alias_streams_bytes() -> None:
    app = create_app()
    app.state.skill_download_tag_reader = lambda namespace, slug, tag, current_user_id: DownloadResult(
        content=b"web-tag",
        content_type="application/zip",
        filename="Demo-1.0.0.zip",
    )

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/tags/stable/download")

    assert response.status_code == 200
    assert response.content == b"web-tag"


def test_tag_download_route_uses_session_principal() -> None:
    seen: list[str | None] = []
    app = create_app()
    app.state.local_auth_login = lambda payload: session_principal()

    def reader(namespace: str, slug: str, tag: str, current_user_id: str | None) -> DownloadResult:
        seen.append(current_user_id)
        return DownloadResult(content=b"tag", content_type="application/zip", filename="Demo-1.0.0.zip")

    app.state.skill_download_tag_reader = reader

    client = TestClient(app)
    client.post("/api/v1/auth/local/login", json={"username": "local-user", "password": "Abcd123!"})
    response = client.get("/api/web/skills/team-ai/demo/tags/stable/download")

    assert response.status_code == 200
    assert seen == ["local-user"]


def test_portal_download_route_maps_reader_error_to_http_status() -> None:
    app = create_app()

    def reader(namespace: str, slug: str, current_user_id: str | None) -> DownloadResult:
        raise SkillResolveError("error.skill.bundle.notFound", status_code=404)

    app.state.skill_download_latest_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "error.skill.bundle.notFound"


def test_build_download_response_sets_java_compatible_headers() -> None:
    response = build_download_response(DownloadResult(content=b"abc", content_type="application/zip", filename="A.zip"))

    assert response.body == b"abc"
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-length"] == "3"
    assert response.headers["content-disposition"] == 'attachment; filename="A.zip"'


@dataclass
class FakeDbResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    scalar: Any = None

    def mappings(self) -> "FakeDbResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeDownloadConnection:
    def __init__(self, results: list[FakeDbResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeDbResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        return self.results.pop(0)


class FakeDownloadContext:
    def __init__(self, connection: FakeDownloadConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeDownloadConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeDownloadEngine:
    def __init__(self, connection: FakeDownloadConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeDownloadContext:
        return FakeDownloadContext(self.connection)

    def connect(self) -> FakeDownloadContext:
        return FakeDownloadContext(self.connection)


@pytest.mark.anyio
async def test_download_version_allows_private_skill_for_namespace_manager(tmp_path) -> None:
    file_path = tmp_path / "skills" / "7" / "42" / "SKILL.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"# private\n")
    connection = FakeDownloadConnection(
        [
            FakeDbResult(
                row={
                    "id": 7,
                    "owner_id": "owner-user",
                    "namespace_id": 10,
                    "slug": "private-demo",
                    "display_name": "Private Demo",
                }
            ),
            FakeDbResult(scalar="ADMIN"),
            FakeDbResult(row={"id": 42, "version": "1.0.0", "status": "UPLOADED"}),
            FakeDbResult(rows=[{"file_path": "SKILL.md", "storage_key": "skills/7/42/SKILL.md"}]),
        ]
    )

    result = await read_skill_download_version(
        FakeDownloadEngine(connection),
        str(tmp_path),
        "team-ai",
        "private-demo",
        "1.0.0",
        "local-admin",
    )

    assert result.filename == "Private Demo-1.0.0.zip"
    with ZipFile(result.as_bytes_io()) as archive:
        assert archive.namelist() == ["SKILL.md"]
        assert archive.read("SKILL.md") == b"# private\n"
    assert "s.visibility = 'PUBLIC'" not in connection.statements[0]


@pytest.mark.anyio
async def test_published_download_records_local_download_event(tmp_path) -> None:
    bundle = tmp_path / "packages" / "7" / "42" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"published-bundle")
    connection = FakeDownloadConnection(
        [
            FakeDbResult(
                row={
                    "id": 7,
                    "owner_id": "owner-user",
                    "namespace_id": 10,
                    "slug": "published-demo",
                    "display_name": "Published Demo",
                }
            ),
            FakeDbResult(scalar=None),
            FakeDbResult(row={"id": 42, "version": "1.0.0", "status": "PUBLISHED", "download_ready": True, "yanked_at": None}),
            FakeDbResult(rows=[]),
            FakeDbResult(),
            FakeDbResult(),
            FakeDbResult(),
        ]
    )

    result = await read_skill_download_version(
        FakeDownloadEngine(connection),
        str(tmp_path),
        "team-ai",
        "published-demo",
        "1.0.0",
        "local-user",
        download_event_context=SimpleNamespace(
            user_id="local-user",
            source="web",
            request_id="request-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
    )

    assert result.content == b"published-bundle"
    assert any("UPDATE skill SET download_count" in statement for statement in connection.statements)
    assert any("INSERT INTO skill_version_stats" in statement for statement in connection.statements)
    assert any("INSERT INTO local_skill_download_event" in statement for statement in connection.statements)
    assert connection.params[-1] == {
        "skill_id": 7,
        "skill_version_id": 42,
        "user_id": "local-user",
        "namespace": "team-ai",
        "slug": "published-demo",
        "version": "1.0.0",
        "source": "web",
        "request_id": "request-1",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
    }


@pytest.mark.anyio
async def test_preview_download_does_not_record_local_download_event(tmp_path) -> None:
    file_path = tmp_path / "skills" / "7" / "42" / "SKILL.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"# preview\n")
    connection = FakeDownloadConnection(
        [
            FakeDbResult(
                row={
                    "id": 7,
                    "owner_id": "owner-user",
                    "namespace_id": 10,
                    "slug": "preview-demo",
                    "display_name": "Preview Demo",
                }
            ),
            FakeDbResult(scalar="ADMIN"),
            FakeDbResult(row={"id": 42, "version": "1.0.0", "status": "UPLOADED", "download_ready": False, "yanked_at": None}),
            FakeDbResult(rows=[{"file_path": "SKILL.md", "storage_key": "skills/7/42/SKILL.md"}]),
        ]
    )

    result = await read_skill_download_version(
        FakeDownloadEngine(connection),
        str(tmp_path),
        "team-ai",
        "preview-demo",
        "1.0.0",
        "local-admin",
        download_event_context=SimpleNamespace(
            user_id="local-admin",
            source="web",
            request_id="request-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
    )

    assert result.filename == "Preview Demo-1.0.0.zip"
    assert not any("INSERT INTO local_skill_download_event" in statement for statement in connection.statements)


@pytest.mark.parametrize(
    ("path", "expected_source"),
    [
        ("/api/v1/skills/team-ai/demo/download", "api"),
        ("/api/web/skills/team-ai/demo/download", "web"),
        ("/api/cli/v1/skills/team-ai/demo/download", "cli"),
    ],
)
def test_download_routes_pass_local_download_event_source(monkeypatch, path: str, expected_source: str) -> None:
    import app.api.skills as skills_api

    app = create_app()
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/unused")
    seen: list[Any] = []

    async def fake_read_skill_download_latest(
        engine: object,
        storage_base_path: str,
        namespace: str,
        slug: str,
        current_user_id: str | None = None,
        installable_only: bool = False,
        download_event_context: object | None = None,
    ) -> DownloadResult:
        seen.append(download_event_context)
        return DownloadResult(content=b"bundle", content_type="application/zip", filename="Demo-1.0.0.zip")

    monkeypatch.setattr(skills_api, "read_skill_download_latest", fake_read_skill_download_latest)

    client = TestClient(app)
    response = client.get(path, headers={"X-Mock-User-Id": " local-user "})

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0].source == expected_source
    assert seen[0].user_id == "local-user"


def test_download_resolution_queries_do_not_hardcode_public_visibility() -> None:
    source = "\n".join(
        [
            inspect.getsource(read_skill_download_version),
            inspect.getsource(read_skill_download_latest),
            inspect.getsource(read_skill_download_tag),
        ]
    )

    assert "s.visibility = 'PUBLIC'" not in source
