from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.api.skills import DownloadResult
from app.main import create_app
from app.publish.dry_run import PublishDryRunResult
from app.publish.orchestration import PublishWriteResult
from app.publish.side_effects import PublishSideEffectResult
from app.publish.storage import StoredPackageResult


def skill_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            b"---\nname: CLI Skill\ndescription: Tests CLI backend flow\nversion: 1.0.0\n---\n# CLI\n",
        )
        archive.writestr("src/main.py", b"print('cli')\n")
    return buffer.getvalue()


def mock_user(user_id: str) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_cli_bearer_user_can_search_resolve_download_validate_and_publish() -> None:
    app = create_app()
    flow: list[tuple[object, ...]] = []
    app.state.auth_bearer_reader = lambda token: mock_user("cli-user") if token == "sk_valid" else None
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-cli-flow-test-storage",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    app.state.publish_write_namespace_id = 30

    def search_reader(**kwargs: object) -> dict[str, object]:
        flow.append(("search", kwargs))
        return {
            "items": [
                {
                    "slug": "cli-skill",
                    "displayName": "CLI Skill",
                    "summary": "CLI flow summary",
                    "namespace": "global",
                    "downloadCount": 3,
                    "starCount": 0,
                    "ratingAvg": 0,
                    "ratingCount": 0,
                    "publishedVersion": {"id": 52, "version": "1.0.0", "status": "PUBLISHED"},
                    "updatedAt": "2026-06-20T10:00:00Z",
                }
            ],
            "total": 1,
            "page": 0,
            "size": 10,
        }

    def resolve_reader(namespace, slug, version, tag, hash_value, current_user_id=None):
        flow.append(("resolve", namespace, slug, version, tag, hash_value, current_user_id))
        return {
            "skillId": 17,
            "namespace": namespace,
            "slug": slug,
            "version": version or "1.0.0",
            "versionId": 52,
            "fingerprint": "sha256:cli",
            "matched": True,
            "downloadUrl": f"/api/v1/skills/{namespace}/{slug}/versions/{version or '1.0.0'}/download",
        }

    def download_reader(namespace, slug, current_user_id):
        flow.append(("download", namespace, slug, current_user_id))
        return DownloadResult(
            content=b"cli-bundle",
            content_type="application/zip",
            filename="CLI Skill-1.0.0.zip",
        )

    async def validate_reader(namespace, entries, publisher_id, visibility, platform_roles):
        flow.append(
            (
                "validate",
                namespace,
                [entry.path for entry in entries],
                publisher_id,
                visibility,
                sorted(platform_roles),
            )
        )
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="cli-skill",
            resolved_version="1.0.0",
        )

    async def write_reader(write_input):
        flow.append(
            (
                "publish",
                write_input.namespace_slug,
                write_input.publisher_id,
                write_input.visibility,
                write_input.scanner_enabled,
            )
        )
        return PublishWriteResult(
            skill_id=17,
            version_id=52,
            version_status="PENDING_REVIEW",
            latest_version_updated=False,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/17/52/bundle.zip",
                bundle_size=64,
                file_count=2,
                total_size=96,
                bundle_ready=True,
                download_ready=True,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=901,
                security_audit_id=None,
                scan_task=None,
                events=[],
            ),
            replacement_deleted_keys=[],
            replacement_compensation_recorded=False,
        )

    app.state.cli_skill_search_reader = search_reader
    app.state.skill_resolve_reader = resolve_reader
    app.state.skill_download_latest_reader = download_reader
    app.state.publish_validate_reader = validate_reader
    app.state.publish_write_reader = write_reader

    client = TestClient(app)
    headers = {"Authorization": "Bearer sk_valid"}

    search = client.get("/api/cli/v1/skills/search?q=cli&limit=10", headers=headers)
    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["slug"] == "cli-skill"

    resolve = client.get("/api/cli/v1/skills/global/cli-skill/resolve?version=1.0.0", headers=headers)
    assert resolve.status_code == 200
    assert resolve.json()["data"]["downloadUrl"] == "/api/v1/skills/global/cli-skill/versions/1.0.0/download"

    download = client.get("/api/cli/v1/skills/global/cli-skill/download", headers=headers)
    assert download.status_code == 200
    assert download.content == b"cli-bundle"

    validate = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers=headers,
        data={"visibility": "PRIVATE"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )
    assert validate.status_code == 200
    assert validate.json()["data"]["resolvedSlug"] == "cli-skill"

    publish = client.post(
        "/api/cli/v1/skills/global/publish",
        headers=headers,
        data={"visibility": "PRIVATE"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )
    assert publish.status_code == 200
    assert publish.json()["data"] == {
        "namespace": "global",
        "slug": "cli-skill",
        "version": "1.0.0",
        "visibility": "PRIVATE",
    }

    assert flow == [
        (
            "search",
            {
                "keyword": "cli",
                "namespace": None,
                "labels": [],
                "sort": "newest",
                "page": 0,
                "size": 10,
                "installable_only": True,
                "current_user_id": "cli-user",
            },
        ),
        ("resolve", "global", "cli-skill", "1.0.0", None, None, "cli-user"),
        ("download", "global", "cli-skill", "cli-user"),
        ("validate", "global", ["SKILL.md", "src/main.py"], "cli-user", "PRIVATE", ["USER"]),
        ("validate", "global", ["SKILL.md", "src/main.py"], "cli-user", "PRIVATE", ["USER"]),
        ("publish", "global", "cli-user", "PRIVATE", False),
    ]
