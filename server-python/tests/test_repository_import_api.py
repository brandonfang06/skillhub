from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.collections.access import CollectionAccessError
from app.main import create_app


REPOSITORY_IMPORT_MUTATION_CASES = [
    (
        "POST",
        "/api/web/namespaces/opensource/repository-imports/preview",
        {"projectPath": "oss-mirrors/project", "ref": "main"},
    ),
    (
        "POST",
        "/api/web/repository-imports/9/ingest",
        {
            "candidates": [
                {
                    "candidateId": 1,
                    "targetSlug": "alpha",
                    "targetVersion": "1.0.0",
                    "visibility": "NAMESPACE_ONLY",
                }
            ]
        },
    ),
    (
        "POST",
        "/api/web/repository-imports/9/check-updates",
        None,
    ),
    (
        "POST",
        "/api/web/repository-imports/9/collection-draft",
        {
            "collectionSlug": "superpowers",
            "displayName": "Superpowers",
            "summary": "Curated",
            "candidateIds": [1],
        },
    ),
]


def preview_response() -> dict[str, object]:
    return {
        "import_id": 9,
        "namespace": "opensource",
        "provider": "GITLAB",
        "project_id": "oss-mirrors/project",
        "project_full_path": "oss-mirrors/project",
        "requested_ref": "main",
        "resolved_commit_sha": "a" * 40,
        "source_web_url": "https://gitlab.internal/oss-mirrors/project",
        "upstream_url": None,
        "archive_sha256": "b" * 64,
        "archive_bytes": 10,
        "state": "PREVIEW_READY",
        "candidates": [
            {
                "candidate_id": 1,
                "source_path": "alpha",
                "detected_name": "Alpha",
                "detected_description": "First",
                "source_version": "1.0.0",
                "state": "DISCOVERED",
                "warnings": [],
            }
        ],
    }


def configured_app():
    app = create_app()
    app.state.settings = SimpleNamespace(
        collections_enabled=True,
        gitlab_import_enabled=True,
    )
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "platformRoles": ["USER"],
    }
    return app


def api_token_app(calls: list[str]):
    app = configured_app()
    app.state.auth_bearer_reader = lambda raw_token: (
        {
            "userId": "namespace-owner",
            "oauthProvider": "api_token",
            "tokenScopes": ["skill:read"],
            "platformRoles": ["USER"],
        }
        if raw_token == "sk_read"
        else None
    )

    def writer(*_args):
        calls.append("writer")
        raise AssertionError("repository import writer must not be called")

    def publisher(*_args):
        calls.append("publisher")
        raise AssertionError("repository import publisher must not be called")

    app.state.repository_import_preview_writer = writer
    app.state.repository_import_ingest_writer = writer
    app.state.repository_import_update_writer = writer
    app.state.repository_import_collection_writer = writer
    app.state.repository_import_publish_writer = publisher
    return app


def test_repository_import_routes_are_default_off() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(
        collections_enabled=True,
        gitlab_import_enabled=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/web/namespaces/opensource/repository-imports/preview",
        json={"projectPath": "oss-mirrors/project", "ref": "main"},
        headers={"X-Mock-User-Id": "curator"},
    )

    assert response.status_code == 404


def test_preview_requires_auth_and_never_returns_token() -> None:
    app = configured_app()
    app.state.repository_import_preview_writer = (
        lambda _namespace, _payload, _user, _request: preview_response()
    )
    client = TestClient(app)
    path = "/api/web/namespaces/opensource/repository-imports/preview"

    assert client.post(
        path,
        json={"projectPath": "oss-mirrors/project"},
    ).status_code == 401
    response = client.post(
        path,
        json={"projectPath": "oss-mirrors/project"},
        headers={"X-Mock-User-Id": "curator"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["resolvedCommitSha"] == "a" * 40
    assert "token" not in response.text.lower()


def test_ingest_and_collection_draft_routes_forward_explicit_selection() -> None:
    app = configured_app()
    seen: list[object] = []

    def ingest_writer(import_id, payload, _user, _request):
        seen.append((import_id, payload.candidates[0].target_version))
        return {
            "import_id": import_id,
            "state": "COMPLETED",
            "results": [
                {
                    "candidate_id": 1,
                    "state": "CREATED",
                    "skill_id": 10,
                    "skill_version_id": 11,
                    "version_status": "PUBLISHED",
                }
            ],
        }

    def collection_writer(import_id, payload, _user, _request):
        seen.append((import_id, payload.collection_slug))
        return {
            "collection_slug": payload.collection_slug,
            "draft_revision": 2,
            "member_count": 1,
        }

    app.state.repository_import_ingest_writer = ingest_writer
    app.state.repository_import_collection_writer = collection_writer
    client = TestClient(app)
    headers = {"X-Mock-User-Id": "curator"}
    ingested = client.post(
        "/api/web/repository-imports/9/ingest",
        json={
            "candidates": [
                {
                    "candidateId": 1,
                    "targetSlug": "alpha",
                    "targetVersion": "1.0.0",
                    "visibility": "NAMESPACE_ONLY",
                }
            ]
        },
        headers=headers,
    )
    seeded = client.post(
        "/api/web/repository-imports/9/collection-draft",
        json={
            "collectionSlug": "superpowers",
            "displayName": "Superpowers",
            "summary": "Curated",
            "candidateIds": [1],
        },
        headers=headers,
    )

    assert ingested.status_code == 200
    assert seeded.status_code == 200
    assert seen == [(9, "1.0.0"), (9, "superpowers")]


def test_collection_draft_route_rejects_more_than_one_hundred_candidates() -> None:
    app = configured_app()
    calls = 0

    def collection_writer(*_args):
        nonlocal calls
        calls += 1
        return {}

    app.state.repository_import_collection_writer = collection_writer
    response = TestClient(app).post(
        "/api/web/repository-imports/9/collection-draft",
        json={
            "collectionSlug": "oversized",
            "displayName": "Oversized",
            "summary": "Too many candidates",
            "candidateIds": list(range(101)),
        },
        headers={"X-Mock-User-Id": "curator"},
    )

    assert response.status_code == 422
    assert calls == 0


def test_update_check_route_returns_linked_preview_without_token() -> None:
    app = configured_app()
    app.state.repository_import_update_writer = (
        lambda import_id, _user, _request: {
            "previous_import_id": import_id,
            "changed": True,
            "previous_commit_sha": "a" * 40,
            "current_commit_sha": "b" * 40,
            "preview": {
                **preview_response(),
                "import_id": 10,
                "previous_import_id": import_id,
                "resolved_commit_sha": "b" * 40,
            },
        }
    )

    response = TestClient(app).post(
        "/api/web/repository-imports/9/check-updates",
        headers={"X-Mock-User-Id": "curator"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["changed"] is True
    assert response.json()["data"]["preview"]["previousImportId"] == 9
    assert "token" not in response.text.lower()


def test_repository_import_openapi_is_typed() -> None:
    schema = create_app().openapi()

    assert "/api/web/namespaces/{namespace}/repository-imports/preview" in schema["paths"]
    assert "/api/web/repository-imports/{import_id}/ingest" in schema["paths"]
    assert "/api/web/repository-imports/{import_id}/collection-draft" in schema["paths"]
    assert "/api/web/repository-imports/{import_id}/check-updates" in schema["paths"]
    assert "RepositoryImportPreviewRequest" in schema["components"]["schemas"]
    assert "RepositoryImportUpdateCheckResponse" in schema["components"]["schemas"]


def test_namespace_member_denial_remains_a_backend_403() -> None:
    app = configured_app()

    def denied(*_args, **_kwargs):
        raise CollectionAccessError(
            "error.collection.curator.required",
            status_code=403,
        )

    app.state.repository_import_preview_writer = denied
    response = TestClient(app).post(
        "/api/web/namespaces/opensource/repository-imports/preview",
        json={"projectPath": "oss-mirrors/project"},
        headers={"X-Mock-User-Id": "member"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.collection.curator.required"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    REPOSITORY_IMPORT_MUTATION_CASES,
)
def test_repository_import_mutations_reject_read_only_api_token_before_writes(
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    calls: list[str] = []
    client = TestClient(api_token_app(calls), raise_server_exceptions=False)

    response = (
        client.request(method, path, headers={"Authorization": "Bearer sk_read"})
        if body is None
        else client.request(
            method,
            path,
            headers={"Authorization": "Bearer sk_read"},
            json=body,
        )
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        f"API token cannot access endpoint: {response.request.url.path}"
    )
    assert calls == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    REPOSITORY_IMPORT_MUTATION_CASES,
)
def test_repository_import_mutations_keep_invalid_bearer_unauthorized(
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    calls: list[str] = []
    client = TestClient(api_token_app(calls), raise_server_exceptions=False)

    response = (
        client.request(
            method,
            path,
            headers={"Authorization": "Bearer sk_invalid"},
        )
        if body is None
        else client.request(
            method,
            path,
            headers={"Authorization": "Bearer sk_invalid"},
            json=body,
        )
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
    assert calls == []
