from zipfile import ZipFile

from fastapi.testclient import TestClient

import pytest

from app.api.skills import (
    DownloadResult,
    SkillResolveError,
    assert_download_access,
    build_download_filename,
    build_download_response,
    read_bundle_or_build_fallback_zip,
    sanitize_download_filename,
)
from app.main import create_app


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
