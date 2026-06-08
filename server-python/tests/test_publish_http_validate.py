from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.publish.orchestration import PublishWriteResult
from app.publish.replacement import ReplaceableVersion
from app.publish.dry_run import PublishDryRunResult
from app.publish.package import PackageEntry
from app.publish.side_effects import PublishSideEffectResult
from app.publish.storage import StoredPackageResult


def skill_zip(skill_md: bytes | None = None) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            skill_md
            or b"---\nname: Agent Helper\ndescription: Helps agents\nversion: 1.0.0\n---\n# Skill\n",
        )
        archive.writestr("src/main.py", b"print('ok')\n")
    return buffer.getvalue()


def auth_user(platform_roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": "local-user",
        "displayName": "Local User",
        "email": "local-user@example.com",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": platform_roles or ["USER"],
    }


def test_cli_publish_validate_requires_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 401


def test_cli_publish_validate_rejects_invalid_visibility() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user()
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers={"X-Mock-User-Id": "local-user"},
        data={"visibility": "TEAM_ONLY"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.skill.publish.visibility.invalid"


def test_cli_publish_validate_returns_java_compatible_dry_run_envelope() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])
    seen: dict[str, object] = {}

    async def reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        seen["namespace"] = namespace
        seen["paths"] = [entry.path for entry in entries]
        seen["publisher_id"] = publisher_id
        seen["visibility"] = visibility
        seen["platform_roles"] = sorted(platform_roles)
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    app.state.publish_validate_reader = reader
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "publish-validate-test"},
        data={"visibility": "private"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "response.success.read"
    assert body["requestId"] == "publish-validate-test"
    assert body["data"] == {
        "valid": True,
        "errors": [],
        "warnings": [],
        "resolvedSlug": "agent-helper",
        "resolvedVersion": "1.0.0",
    }
    assert seen == {
        "namespace": "global",
        "paths": ["SKILL.md", "src/main.py"],
        "publisher_id": "local-user",
        "visibility": "PRIVATE",
        "platform_roles": ["SUPER_ADMIN"],
    }


def test_cli_publish_write_attaches_replaceable_version_before_write() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])
    seen: dict[str, object] = {}

    async def validate_reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    async def replacement_reader(
        namespace_id: int,
        namespace: str,
        slug: str,
        version: str,
        publisher_id: str,
    ) -> ReplaceableVersion:
        seen["replacement_args"] = {
            "namespace_id": namespace_id,
            "namespace": namespace,
            "slug": slug,
            "version": version,
            "publisher_id": publisher_id,
        }
        return ReplaceableVersion(
            skill_id=7,
            namespace=namespace,
            slug=slug,
            version_id=41,
            version=version,
            status="UPLOADED",
            publisher_id=publisher_id,
            latest_version_id=41,
        )

    async def write_reader(request: object) -> PublishWriteResult:
        replacement = getattr(request, "replacement")
        seen["replacement"] = replacement
        return PublishWriteResult(
            skill_id=7,
            version_id=42,
            version_status="PUBLISHED",
            latest_version_updated=True,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/7/42/bundle.zip",
                bundle_size=10,
                file_count=2,
                total_size=20,
                bundle_ready=True,
                download_ready=True,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=None,
                security_audit_id=None,
                scan_task=None,
                events=[],
            ),
            replacement_deleted_keys=["skills/7/41/SKILL.md", "packages/7/41/bundle.zip"],
            replacement_compensation_recorded=False,
        )

    app.state.publish_validate_reader = validate_reader
    app.state.publish_replacement_reader = replacement_reader
    app.state.publish_write_reader = write_reader
    app.state.publish_write_namespace_id = 10
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-storage",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish",
        headers={"X-Mock-User-Id": "local-user"},
        data={"visibility": "PUBLIC"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    assert seen["replacement_args"] == {
        "namespace_id": 10,
        "namespace": "global",
        "slug": "agent-helper",
        "version": "1.0.0",
        "publisher_id": "local-user",
    }
    assert isinstance(seen["replacement"], ReplaceableVersion)
    assert seen["replacement"].version_id == 41


def test_cli_publish_write_requires_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish",
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 401


def test_cli_publish_write_rejects_invalid_preflight_before_write() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user()
    writer_called = False

    async def validate_reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        return PublishDryRunResult(
            valid=False,
            errors=["Publisher is not a member of namespace: global"],
            warnings=[],
            resolved_slug=None,
            resolved_version=None,
        )

    async def write_reader(*args: object, **kwargs: object) -> PublishWriteResult:
        nonlocal writer_called
        writer_called = True
        raise AssertionError("write must not run")

    app.state.publish_validate_reader = validate_reader
    app.state.publish_write_reader = write_reader
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish",
        headers={"X-Mock-User-Id": "local-user"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Publisher is not a member of namespace: global"
    assert not writer_called


def test_cli_publish_write_returns_java_compatible_publish_envelope() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])
    seen: dict[str, object] = {}

    async def validate_reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    async def write_reader(request: object) -> PublishWriteResult:
        seen["slug"] = getattr(request, "slug")
        seen["version"] = getattr(request, "version")
        seen["visibility"] = getattr(request, "visibility")
        seen["auto_publish"] = getattr(request, "auto_publish")
        seen["publisher_id"] = getattr(request, "publisher_id")
        seen["scanner_enabled"] = getattr(request, "scanner_enabled")
        seen["scan_mode"] = getattr(request, "scan_mode")
        return PublishWriteResult(
            skill_id=7,
            version_id=42,
            version_status="PUBLISHED",
            latest_version_updated=True,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/7/42/bundle.zip",
                bundle_size=10,
                file_count=2,
                total_size=20,
                bundle_ready=True,
                download_ready=True,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=None,
                security_audit_id=None,
                scan_task=None,
                events=[],
            ),
            replacement_deleted_keys=[],
            replacement_compensation_recorded=False,
        )

    app.state.publish_validate_reader = validate_reader
    app.state.publish_write_reader = write_reader
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-storage",
        security_scanner_enabled=True,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "publish-write-test"},
        data={"visibility": "PUBLIC"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "response.success.published"
    assert body["requestId"] == "publish-write-test"
    assert body["data"] == {
        "namespace": "global",
        "slug": "agent-helper",
        "version": "1.0.0",
        "visibility": "PUBLIC",
    }
    assert seen == {
        "slug": "agent-helper",
        "version": "1.0.0",
        "visibility": "PUBLIC",
        "auto_publish": True,
        "publisher_id": "local-user",
        "scanner_enabled": True,
        "scan_mode": "upload",
    }
