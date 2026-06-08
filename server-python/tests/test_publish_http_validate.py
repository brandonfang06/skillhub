from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.publish.dry_run import PublishDryRunResult
from app.publish.package import PackageEntry


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
