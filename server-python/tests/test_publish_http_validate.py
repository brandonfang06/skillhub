from __future__ import annotations

import json
import logging
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api import publish as publish_api
from app.main import create_app
from app.publish.orchestration import PublishWriteResult
from app.publish.replacement import ReplaceableVersion, VersionReplacementConflict
from app.publish.dry_run import PublishDryRunResult
from app.publish.package import PackageEntry
from app.publish.side_effects import PublishSideEffectResult
from app.publish.storage import StoredPackageResult
from tests.support.builders import auth_user as build_auth_user
from tests.support.builders import bearer_user as build_bearer_user


def skill_zip(skill_md: bytes | None = None, skill_path: str = "SKILL.md") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            skill_path,
            skill_md
            or b"---\nname: Agent Helper\ndescription: Helps agents\nversion: 1.0.0\n---\n# Skill\n",
        )
        archive.writestr("src/main.py", b"print('ok')\n")
    return buffer.getvalue()


def auth_user(platform_roles: list[str] | None = None) -> dict[str, object]:
    user = build_auth_user("local-user", platform_roles=platform_roles)
    user["displayName"] = "Local User"
    user["email"] = "local-user@example.com"
    return user


def bearer_user(scopes: list[str] | None = None, platform_roles: list[str] | None = None) -> dict[str, object]:
    user = build_bearer_user("token-user", scopes if scopes is not None else ["skill:publish"])
    user["displayName"] = "Token User"
    user["email"] = "token-user@example.com"
    user["platformRoles"] = platform_roles or ["USER"]
    return user


def install_publish_validate_reader(app: object, seen: dict[str, object] | None = None) -> None:
    async def reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        if seen is not None:
            seen["namespace"] = namespace
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


@pytest.mark.anyio
async def test_scanner_enabled_publish_write_does_not_create_request_path_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    app.state.db_engine = object()
    expected = object()
    seen: dict[str, object] = {}

    async def execute(engine: object, write_input: object, **kwargs: object) -> object:
        seen["engine"] = engine
        seen["write_input"] = write_input
        seen["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(publish_api, "execute_publish_write", execute)
    request = SimpleNamespace(app=app)
    write_input = SimpleNamespace(scanner_enabled=True)

    result = await publish_api.run_publish_write(request, write_input)

    assert result is expected
    assert seen["engine"] is app.state.db_engine
    assert not hasattr(app.state, "redis_client")


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


def test_cli_publish_validate_canonicalizes_case_insensitive_skill_md() -> None:
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
        seen["paths"] = [entry.path for entry in entries]
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
        headers={"X-Mock-User-Id": "local-user"},
        files={"file": ("skill.zip", skill_zip(skill_path="skill.md"), "application/zip")},
    )

    assert response.status_code == 200
    assert seen["paths"] == ["SKILL.md", "src/main.py"]


def test_cli_publish_validate_accepts_bearer_with_publish_scope() -> None:
    app = create_app()
    seen: dict[str, object] = {}
    app.state.auth_bearer_reader = lambda raw_token: bearer_user(["skill:read", "skill:publish"], ["SUPER_ADMIN"])
    install_publish_validate_reader(app, seen)
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers={"Authorization": "Bearer sk_publish"},
        data={"visibility": "private"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["valid"] is True
    assert seen == {
        "namespace": "global",
        "publisher_id": "token-user",
        "visibility": "PRIVATE",
        "platform_roles": ["SUPER_ADMIN"],
    }


def test_publish_routes_reject_bearer_without_publish_scope_before_service_call() -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda raw_token: bearer_user(["skill:read"], ["SUPER_ADMIN"])
    app.state.publish_validate_reader = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("publish service should not be called")
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer sk_readonly"}

    cases = [
        (
            "/api/cli/v1/skills/global/publish/validate",
            {"visibility": "PUBLIC"},
            {"file": ("skill.zip", skill_zip(), "application/zip")},
        ),
        (
            "/api/cli/v1/skills/global/publish",
            {"visibility": "PUBLIC"},
            {"file": ("skill.zip", skill_zip(), "application/zip")},
        ),
        (
            "/api/v1/skills/global/publish",
            {"visibility": "PUBLIC"},
            {"file": ("skill.zip", skill_zip(), "application/zip")},
        ),
        (
            "/api/web/skills/global/publish",
            {"visibility": "PUBLIC"},
            {"file": ("skill.zip", skill_zip(), "application/zip")},
        ),
        (
            "/api/v1/publish",
            {"namespace": "global"},
            {"file": ("skill.zip", skill_zip(), "application/zip")},
        ),
    ]
    for path, data, files in cases:
        response = client.post(path, headers=headers, data=data, files=files)
        assert response.status_code == 403
        payload = response.json()
        assert payload["msg"] == "error.apiToken.scope.missing"
        assert payload["data"]["args"] == ["skill:publish"]
        assert payload["requestId"] == response.headers["X-Request-Id"]

    response = client.post(
        "/api/v1/skills",
        headers=headers,
        data={"payload": json.dumps({"slug": "agent-helper"})},
        files=[("files", ("SKILL.md", b"---\nname: Agent Helper\ndescription: Helps\n---\n# Skill\n", "text/markdown"))],
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["msg"] == "error.apiToken.scope.missing"
    assert payload["data"]["args"] == ["skill:publish"]
    assert payload["requestId"] == response.headers["X-Request-Id"]


def test_publish_routes_reject_bad_bearer() -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda raw_token: None
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers={"Authorization": "Bearer sk_missing"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


def test_publish_routes_keep_mock_precedence_over_bearer_scope() -> None:
    app = create_app()
    seen_bearer_tokens: list[str] = []
    seen: dict[str, object] = {}

    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])

    def bearer_reader(raw_token: str) -> dict[str, object]:
        seen_bearer_tokens.append(raw_token)
        return bearer_user(["skill:read"])

    app.state.auth_bearer_reader = bearer_reader
    install_publish_validate_reader(app, seen)
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/skills/global/publish/validate",
        headers={"X-Mock-User-Id": "local-user", "Authorization": "Bearer sk_readonly"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    assert seen["publisher_id"] == "local-user"
    assert seen_bearer_tokens == []


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


def test_cli_publish_write_forces_rejected_version_resubmission_through_review() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])
    replacement_called = False
    writer_called = False

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
        nonlocal replacement_called
        replacement_called = True
        return ReplaceableVersion(
            skill_id=7,
            namespace=namespace,
            slug=slug,
            version_id=41,
            version=version,
            status="REJECTED",
            publisher_id=publisher_id,
        )

    async def write_reader(request: object) -> PublishWriteResult:
        nonlocal writer_called
        writer_called = True
        assert getattr(request, "replacement").status == "REJECTED"
        assert getattr(request, "auto_publish") is False
        return PublishWriteResult(
            skill_id=7,
            version_id=42,
            version_status="PENDING_REVIEW",
            latest_version_updated=False,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/7/42/bundle.zip",
                bundle_size=10,
                file_count=2,
                total_size=20,
                bundle_ready=True,
                download_ready=False,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=900,
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
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    assert replacement_called
    assert writer_called
    assert response.json()["data"]["version"] == "1.0.0"
    assert response.json()["data"]["status"] == "PENDING_REVIEW"


def test_cli_publish_strict_mode_refuses_a_replaceable_existing_version() -> None:
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
        return ReplaceableVersion(
            skill_id=7,
            namespace=namespace,
            slug=slug,
            version_id=41,
            version=version,
            status="UPLOADED",
            publisher_id=publisher_id,
        )

    async def write_reader(request: object) -> PublishWriteResult:
        nonlocal writer_called
        writer_called = True
        raise AssertionError("strict conflict must not reach the writer")

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

    response = TestClient(app).post(
        "/api/cli/v1/skills/global/publish",
        headers={"X-Mock-User-Id": "local-user"},
        data={"rejectExistingVersion": "true"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "error.skill.version.exists"
    assert writer_called is False


def test_cli_publish_write_maps_ineligible_replacement_race_to_conflict() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user()

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

    async def write_reader(*args: object, **kwargs: object) -> PublishWriteResult:
        raise VersionReplacementConflict("error.skill.version.exists")

    app.state.publish_validate_reader = validate_reader
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
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "error.skill.version.exists"


def test_cli_publish_write_logs_invalid_preflight_for_forensics(caplog) -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user()

    async def validate_reader(
        namespace: str,
        entries: list[PackageEntry],
        publisher_id: str,
        visibility: str,
        platform_roles: set[str],
    ) -> PublishDryRunResult:
        return PublishDryRunResult(
            valid=False,
            errors=[],
            warnings=["Disallowed file extension: docs/flow.dot"],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    app.state.publish_validate_reader = validate_reader
    client = TestClient(app)
    caplog.set_level(logging.WARNING, logger="uvicorn.error")

    response = client.post(
        "/api/cli/v1/skills/global/publish",
        headers={"X-Mock-User-Id": "local-user", "X-Request-Id": "publish-invalid-extension"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Disallowed file extension: docs/flow.dot"
    assert "Skill publish validation rejected" in caplog.text
    assert "request_id=publish-invalid-extension" in caplog.text
    assert "publisher_id=local-user" in caplog.text
    assert "namespace=global" in caplog.text
    assert "warnings=['Disallowed file extension: docs/flow.dot']" in caplog.text


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
        "status": "PUBLISHED",
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


def test_portal_publish_write_aliases_reuse_publish_service() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(["SUPER_ADMIN"])
    seen_paths: list[dict[str, object]] = []

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
        seen_paths.append(
            {
                "namespace_slug": getattr(request, "namespace_slug"),
                "slug": getattr(request, "slug"),
                "version": getattr(request, "version"),
                "visibility": getattr(request, "visibility"),
                "publisher_id": getattr(request, "publisher_id"),
                "auto_publish": getattr(request, "auto_publish"),
            }
        )
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
    app.state.publish_write_namespace_id = 10
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-storage",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    client = TestClient(app)

    for path in ["/api/v1/skills/global/publish", "/api/web/skills/global/publish"]:
        response = client.post(
            path,
            headers={"X-Mock-User-Id": "local-user", "X-Request-Id": f"request-{len(seen_paths)}"},
            data={"visibility": "PRIVATE"},
            files={"file": ("skill.zip", skill_zip(), "application/zip")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["msg"] == "response.success.published"
        assert body["data"] == {
            "namespace": "global",
            "slug": "agent-helper",
            "version": "1.0.0",
            "visibility": "PRIVATE",
            "status": "PUBLISHED",
        }

    assert seen_paths == [
        {
            "namespace_slug": "global",
            "slug": "agent-helper",
            "version": "1.0.0",
            "visibility": "PRIVATE",
            "publisher_id": "local-user",
            "auto_publish": True,
        },
        {
            "namespace_slug": "global",
            "slug": "agent-helper",
            "version": "1.0.0",
            "visibility": "PRIVATE",
            "publisher_id": "local-user",
            "auto_publish": True,
        },
    ]


def test_legacy_publish_route_uses_namespace_form_and_clawhub_response() -> None:
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
        seen["validate"] = {
            "namespace": namespace,
            "publisher_id": publisher_id,
            "visibility": visibility,
            "platform_roles": sorted(platform_roles),
            "paths": [entry.path for entry in entries],
        }
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    async def write_reader(request: object) -> PublishWriteResult:
        seen["write"] = {
            "namespace_slug": getattr(request, "namespace_slug"),
            "visibility": getattr(request, "visibility"),
            "compat_namespace": getattr(request, "compat_namespace"),
            "compat_slug": getattr(request, "compat_slug"),
        }
        return PublishWriteResult(
            skill_id=70,
            version_id=420,
            version_status="PUBLISHED",
            latest_version_updated=True,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/70/420/bundle.zip",
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
        "/api/v1/publish",
        headers={"X-Mock-User-Id": "local-user"},
        data={"namespace": "@team-ai", "confirmWarnings": "true"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "skillId": "70", "versionId": "420"}
    assert seen == {
        "validate": {
            "namespace": "team-ai",
            "publisher_id": "local-user",
            "visibility": "PUBLIC",
            "platform_roles": ["SUPER_ADMIN"],
            "paths": ["SKILL.md", "src/main.py"],
        },
        "write": {
            "namespace_slug": "team-ai",
            "visibility": "PUBLIC",
            "compat_namespace": "team-ai",
            "compat_slug": None,
        },
    }


def test_clawhub_root_publish_route_accepts_payload_files_and_clawhub_response() -> None:
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
        seen["validate"] = {
            "namespace": namespace,
            "publisher_id": publisher_id,
            "visibility": visibility,
            "platform_roles": sorted(platform_roles),
            "paths": [entry.path for entry in entries],
            "content_types": [entry.content_type for entry in entries],
        }
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    async def write_reader(request: object) -> PublishWriteResult:
        seen["write"] = {
            "namespace_slug": getattr(request, "namespace_slug"),
            "visibility": getattr(request, "visibility"),
            "compat_namespace": getattr(request, "compat_namespace"),
            "compat_slug": getattr(request, "compat_slug"),
        }
        return PublishWriteResult(
            skill_id=71,
            version_id=421,
            version_status="PUBLISHED",
            latest_version_updated=True,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/71/421/bundle.zip",
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
    app.state.publish_write_namespace_id = 10
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-storage",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    client = TestClient(app)

    payload = {
        "slug": "team-ai--agent-helper",
        "displayName": "Agent Helper",
        "version": "1.0.0",
    }
    response = client.post(
        "/api/v1/skills",
        headers={"X-Mock-User-Id": "local-user"},
        data={"payload": json.dumps(payload), "confirmWarnings": "true"},
        files=[
            (
                "files",
                (
                    "SKILL.md",
                    b"---\nname: Agent Helper\ndescription: Helps agents\nversion: 1.0.0\n---\n# Skill\n",
                    "text/markdown",
                ),
            ),
            ("files", ("src/main.py", b"print('ok')\n", "text/x-python")),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "skillId": "71", "versionId": "421"}
    assert seen == {
        "validate": {
            "namespace": "team-ai",
            "publisher_id": "local-user",
            "visibility": "PUBLIC",
            "platform_roles": ["SUPER_ADMIN"],
            "paths": ["SKILL.md", "src/main.py"],
            "content_types": ["text/markdown", "text/x-python"],
        },
        "write": {
            "namespace_slug": "team-ai",
            "visibility": "PUBLIC",
            "compat_namespace": "team-ai",
            "compat_slug": "team-ai--agent-helper",
        },
    }


def test_clawhub_root_publish_route_canonicalizes_case_insensitive_skill_md_file() -> None:
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
        seen["paths"] = [entry.path for entry in entries]
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="agent-helper",
            resolved_version="1.0.0",
        )

    async def write_reader(request: object) -> PublishWriteResult:
        seen["write_paths"] = [entry.path for entry in getattr(request, "entries")]
        return PublishWriteResult(
            skill_id=71,
            version_id=421,
            version_status="PUBLISHED",
            latest_version_updated=True,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/71/421/bundle.zip",
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
        "/api/v1/skills",
        headers={"X-Mock-User-Id": "local-user"},
        data={"payload": json.dumps({"slug": "team-ai--agent-helper"}), "confirmWarnings": "true"},
        files=[
            (
                "files",
                (
                    "skill.md",
                    b"---\nname: Agent Helper\ndescription: Helps agents\nversion: 1.0.0\n---\n# Skill\n",
                    "text/markdown",
                ),
            ),
            ("files", ("src/main.py", b"print('ok')\n", "text/x-python")),
        ],
    )

    assert response.status_code == 200
    assert seen["paths"] == ["SKILL.md", "src/main.py"]
    assert seen["write_paths"] == ["SKILL.md", "src/main.py"]
