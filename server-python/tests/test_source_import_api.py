from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.source_import.contracts import SourcePackage
from app.source_import.service import (
    EnsureSourceNamespaceResult,
    IdentityAccount,
    NamespaceRecord,
    NamespaceSourceBinding,
    SourceSkillSubmissionResult,
    SourceSkillValidationPlan,
)
from tests.support.builders import bearer_user as build_bearer_user


def skill_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            "---\nname: Code Review\ndescription: Reviews code\n---\n# Code Review\n",
        )
    return buffer.getvalue()


def token_user(*, scopes: list[str] | None = None, roles: list[str] | None = None) -> dict[str, object]:
    user = build_bearer_user("importer-service", scopes or ["source:import"])
    user["displayName"] = "Importer Service"
    user["platformRoles"] = roles or ["SKILL_ADMIN"]
    return user


def ensure_result() -> EnsureSourceNamespaceResult:
    return EnsureSourceNamespaceResult(
        "CREATED",
        NamespaceRecord(10, "oss-mattpocock-skills", "OSS-mattpocock-skills", "TEAM", "ACTIVE"),
        NamespaceSourceBinding(20, 10, "https://github.com/mattpocock/skills"),
        IdentityAccount("owner-id", "Platform Owner", "ACTIVE", "keycloak", "platform-owner"),
    )


def validation_plan() -> SourceSkillValidationPlan:
    entries = []
    owner = IdentityAccount("owner-id", "Platform Owner", "ACTIVE", "keycloak", "platform-owner")
    return SourceSkillValidationPlan(
        outcome="IMPORT",
        namespace=ensure_result().namespace,
        namespace_binding=ensure_result().binding,
        source_skill=None,
        package=SourcePackage(
            source_path="skills/code-review",
            entries=entries,
            metadata=SimpleNamespace(name="Code Review", description="Reviews code", version=None, frontmatter={}),
            content_fingerprint="f" * 64,
            effective_version="git-" + "a" * 40,
        ),
        skill_slug="code-review",
        stable_owner=owner,
        review_submitter=owner,
        add_submitter_as_member=False,
    )


def metadata_payload(**changes: object) -> str:
    payload: dict[str, object] = {
        "repositoryUrl": "https://github.com/mattpocock/skills",
        "repositoryRevisionSha": "a" * 40,
        "sourceRefType": "BRANCH",
        "sourceRef": "main",
        "sourcePath": "skills/code-review",
        "versionOverride": "git-" + "a" * 40,
        "initiatorProviderCode": "keycloak",
        "initiatorLoginName": "alice",
        "pipelineId": "100",
        "jobId": "200",
        "ciRefName": "main",
    }
    payload.update(changes)
    return json.dumps(payload)


def install_bearer(app: object, user: dict[str, object]) -> None:
    app.state.auth_bearer_reader = lambda _token: user


def test_source_import_routes_require_bearer_api_token() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-mattpocock-skills",
        json={
            "repositoryUrl": "https://github.com/mattpocock/skills",
            "displayName": "OSS-mattpocock-skills",
            "fallbackOwnerProviderCode": "keycloak",
            "fallbackOwnerLoginName": "platform-owner",
        },
    )

    assert response.status_code == 401


def test_source_import_routes_reject_non_api_token_bearer_principal() -> None:
    app = create_app()
    user = token_user()
    user["oauthProvider"] = "keycloak"
    install_bearer(app, user)
    client = TestClient(app)

    response = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-mattpocock-skills",
        headers={"Authorization": "Bearer session-token"},
        json={
            "repositoryUrl": "https://github.com/mattpocock/skills",
            "displayName": "OSS-mattpocock-skills",
            "fallbackOwnerProviderCode": "keycloak",
            "fallbackOwnerLoginName": "platform-owner",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.sourceImport.apiToken.required"


def test_source_import_routes_require_dedicated_scope_and_platform_role() -> None:
    app = create_app()
    install_bearer(app, token_user(scopes=["skill:publish"]))
    client = TestClient(app)
    body = {
        "repositoryUrl": "https://github.com/mattpocock/skills",
        "displayName": "OSS-mattpocock-skills",
        "fallbackOwnerProviderCode": "keycloak",
        "fallbackOwnerLoginName": "platform-owner",
    }

    missing_scope = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-mattpocock-skills",
        headers={"Authorization": "Bearer api-token"},
        json=body,
    )
    assert missing_scope.status_code == 403
    assert missing_scope.json()["msg"] == "error.apiToken.scope.missing"

    install_bearer(app, token_user(roles=["USER"]))
    missing_role = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-mattpocock-skills",
        headers={"Authorization": "Bearer api-token"},
        json=body,
    )
    assert missing_role.status_code == 403
    assert missing_role.json()["detail"] == "error.sourceImport.platformRole.required"


def test_ensure_namespace_returns_typed_envelope_without_internal_owner_id() -> None:
    app = create_app()
    install_bearer(app, token_user())
    seen: list[object] = []

    async def ensurer(_engine: object, request: object) -> EnsureSourceNamespaceResult:
        seen.append(request)
        return ensure_result()

    app.state.source_import_namespace_ensurer = ensurer
    client = TestClient(app)

    response = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-mattpocock-skills",
        headers={"Authorization": "Bearer api-token"},
        json={
            "repositoryUrl": "https://github.com/mattpocock/skills.git",
            "displayName": "OSS-mattpocock-skills",
            "fallbackOwnerProviderCode": "keycloak",
            "fallbackOwnerLoginName": "platform-owner",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "outcome": "CREATED",
        "namespaceSlug": "oss-mattpocock-skills",
        "displayName": "OSS-mattpocock-skills",
        "status": "ACTIVE",
        "repositoryUrl": "https://github.com/mattpocock/skills",
        "owner": {
            "displayName": "Platform Owner",
            "providerCode": "keycloak",
            "loginName": "platform-owner",
        },
    }
    assert response.json()["requestId"]
    assert len(seen) == 1


def test_ensure_namespace_rejects_derived_path_or_display_mismatch() -> None:
    app = create_app()
    install_bearer(app, token_user())
    client = TestClient(app)

    response = client.put(
        "/api/cli/v1/source-imports/namespaces/oss-other-repo",
        headers={"Authorization": "Bearer api-token"},
        json={
            "repositoryUrl": "https://github.com/mattpocock/skills",
            "displayName": "Wrong display",
            "fallbackOwnerProviderCode": "keycloak",
            "fallbackOwnerLoginName": "platform-owner",
        },
    )

    assert response.status_code == 400


def test_validate_source_skill_parses_zip_and_returns_planned_provenance() -> None:
    app = create_app()
    install_bearer(app, token_user())
    seen: list[object] = []

    async def validator(_engine: object, request: object) -> SourceSkillValidationPlan:
        seen.append(request)
        return validation_plan()

    app.state.source_import_validator = validator
    client = TestClient(app)
    response = client.post(
        "/api/cli/v1/source-imports/oss-mattpocock-skills/skills/validate",
        headers={"Authorization": "Bearer api-token"},
        data={"metadata": metadata_payload()},
        files={"file": ("code-review.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outcome"] == "IMPORT"
    assert data["coordinate"] == "@oss-mattpocock-skills/code-review"
    assert data["version"] == "git-" + "a" * 40
    assert data["sourceProvenance"]["browseUrl"].endswith("/" + "a" * 40 + "/skills/code-review")
    assert len(seen) == 1


def test_validate_source_skill_rejects_unknown_metadata_fields() -> None:
    app = create_app()
    install_bearer(app, token_user())
    client = TestClient(app)

    response = client.post(
        "/api/cli/v1/source-imports/oss-mattpocock-skills/skills/validate",
        headers={"Authorization": "Bearer api-token"},
        data={"metadata": metadata_payload(contentFingerprint="caller-controlled")},
        files={"file": ("code-review.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 400


def test_submit_source_skill_returns_review_state_and_actor() -> None:
    app = create_app()
    install_bearer(app, token_user())

    async def submitter(_engine: object, _request: object, _runtime: object) -> SourceSkillSubmissionResult:
        return SourceSkillSubmissionResult("IMPORTED", validation_plan(), 41, 51, "PENDING_REVIEW", 61)

    app.state.source_import_submitter = submitter
    app.state.settings = SimpleNamespace(
        storage_base_path="ignored",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        publish_allowed_file_extensions=None,
    )
    client = TestClient(app)
    response = client.post(
        "/api/cli/v1/source-imports/oss-mattpocock-skills/skills",
        headers={"Authorization": "Bearer api-token"},
        data={"metadata": metadata_payload()},
        files={"file": ("code-review.zip", skill_zip(), "application/zip")},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outcome"] == "IMPORTED"
    assert data["versionStatus"] == "PENDING_REVIEW"
    assert data["reviewTaskId"] == 61
    assert data["importerActor"]["displayName"] == "Importer Service"
