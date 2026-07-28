from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.collections.access import (
    CollectionAccessError,
    can_curate_collection,
    can_read_collection_member,
    require_collection_curator,
)
from app.collections.contracts import CollectionDraftReplaceRequest, CollectionPublishRequest
from app.main import create_app


COLLECTION_MUTATION_CASES = [
    (
        "POST",
        "/api/web/namespaces/opensource/collections",
        {
            "slug": "superpowers",
            "displayName": "Superpowers",
            "summary": "Curated skills",
        },
        {},
    ),
    (
        "POST",
        "/api/web/collections/opensource/superpowers/draft",
        None,
        {},
    ),
    (
        "PUT",
        "/api/web/collections/opensource/superpowers/draft",
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {
                    "skillId": 80,
                    "skillVersionId": 901,
                    "position": 0,
                }
            ],
        },
        {"If-Match": '"1"'},
    ),
    (
        "DELETE",
        "/api/web/collections/opensource/superpowers/draft",
        None,
        {},
    ),
    (
        "POST",
        "/api/web/collections/opensource/superpowers/publish",
        {"version": "1.2.0", "draftRevision": 2},
        {},
    ),
    (
        "PUT",
        "/api/web/collections/opensource/superpowers/status",
        {"status": "ARCHIVED", "reason": "retired"},
        {},
    ),
]


def _collection_route_app(calls: list[tuple[object, ...]]):
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=True)
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

    def writer(*args):
        calls.append(args)
        raise AssertionError("collection mutation writer must not be called")

    app.state.collection_mutation_writer = writer
    return app


@pytest.mark.parametrize(
    ("namespace_type", "namespace_role", "platform_roles", "expected"),
    [
        ("TEAM", None, [], False),
        ("TEAM", "MEMBER", [], False),
        ("TEAM", "ADMIN", [], True),
        ("TEAM", "OWNER", [], True),
        ("TEAM", None, ["SKILL_ADMIN"], True),
        ("TEAM", None, ["SUPER_ADMIN"], True),
        ("GLOBAL", "OWNER", [], False),
        ("GLOBAL", None, ["SKILL_ADMIN"], True),
        ("GLOBAL", None, ["SUPER_ADMIN"], True),
    ],
)
def test_collection_curator_matrix(
    namespace_type: str,
    namespace_role: str | None,
    platform_roles: list[str],
    expected: bool,
) -> None:
    assert can_curate_collection(namespace_type, namespace_role, platform_roles) is expected


def test_collection_curator_rejects_inactive_namespace_before_mutation() -> None:
    with pytest.raises(CollectionAccessError, match="error.collection.namespace.inactive") as denied:
        require_collection_curator(
            namespace_type="TEAM",
            namespace_status="ARCHIVED",
            namespace_role="OWNER",
            platform_roles=[],
        )

    assert denied.value.status_code == 409


def test_collection_curator_denial_is_forbidden() -> None:
    with pytest.raises(CollectionAccessError, match="error.collection.curator.required") as denied:
        require_collection_curator(
            namespace_type="TEAM",
            namespace_status="ACTIVE",
            namespace_role="MEMBER",
            platform_roles=[],
        )

    assert denied.value.status_code == 403


@pytest.mark.parametrize(
    ("visibility", "user_id", "namespace_role", "platform_roles", "expected"),
    [
        ("PUBLIC", None, None, [], True),
        ("NAMESPACE_ONLY", None, None, [], False),
        ("NAMESPACE_ONLY", "member", "MEMBER", [], True),
        ("PRIVATE", "member", "MEMBER", [], False),
        ("PRIVATE", "admin", "ADMIN", [], True),
        ("PRIVATE", "owner", None, [], True),
        ("PRIVATE", "other", None, ["SUPER_ADMIN"], True),
        ("PRIVATE", "other", None, ["SKILL_ADMIN"], False),
    ],
)
def test_exact_member_read_access_reuses_skill_visibility_rules(
    visibility: str,
    user_id: str | None,
    namespace_role: str | None,
    platform_roles: list[str],
    expected: bool,
) -> None:
    skill = {
        "owner_id": "owner",
        "visibility": visibility,
        "latest_version_id": 99,
    }

    assert can_read_collection_member(
        skill,
        current_user_id=user_id,
        namespace_role=namespace_role,
        platform_roles=platform_roles,
    ) is expected


def test_collection_contracts_expose_camel_case_fields() -> None:
    draft = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "releaseNotes": "Refresh",
            "members": [
                {
                    "skillId": 80,
                    "skillVersionId": 901,
                    "position": 0,
                    "note": None,
                }
            ],
        }
    )
    publish = CollectionPublishRequest.model_validate({"version": "1.2.0", "draftRevision": 3})

    assert draft.display_name == "Superpowers"
    assert draft.members[0].skill_id == 80
    assert draft.members[0].skill_version_id == 901
    assert publish.draft_revision == 3
    assert "draftRevision" in CollectionPublishRequest.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("method", "path", "body", "extra_headers"),
    COLLECTION_MUTATION_CASES,
)
def test_collection_mutations_reject_read_only_api_token_before_writer(
    method: str,
    path: str,
    body: dict[str, object] | None,
    extra_headers: dict[str, str],
) -> None:
    calls: list[tuple[object, ...]] = []
    client = TestClient(
        _collection_route_app(calls),
        raise_server_exceptions=False,
    )
    headers = {"Authorization": "Bearer sk_read", **extra_headers}

    response = (
        client.request(method, path, headers=headers)
        if body is None
        else client.request(method, path, headers=headers, json=body)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        f"API token cannot access endpoint: {response.request.url.path}"
    )
    assert calls == []


@pytest.mark.parametrize(
    ("method", "path", "body", "extra_headers"),
    COLLECTION_MUTATION_CASES,
)
def test_collection_mutations_keep_invalid_bearer_unauthorized(
    method: str,
    path: str,
    body: dict[str, object] | None,
    extra_headers: dict[str, str],
) -> None:
    calls: list[tuple[object, ...]] = []
    client = TestClient(
        _collection_route_app(calls),
        raise_server_exceptions=False,
    )
    headers = {"Authorization": "Bearer sk_invalid", **extra_headers}

    response = (
        client.request(method, path, headers=headers)
        if body is None
        else client.request(method, path, headers=headers, json=body)
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
    assert calls == []
