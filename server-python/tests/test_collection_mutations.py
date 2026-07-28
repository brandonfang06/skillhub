from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.collections.contracts import (
    MAX_COLLECTION_MEMBERS,
    CollectionDraftReplaceRequest,
    CollectionPublishRequest,
    CollectionStatusRequest,
)
from app.collections.service import (
    CollectionMutationError,
    MutationContext,
    SemanticVersion,
    create_collection,
    create_collection_draft,
    delete_collection_draft,
    publish_collection,
    replace_collection_draft,
    set_collection_status,
)
from app.main import create_app
from tests.test_collection_read import api_detail, api_version


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


class FakeEngine:
    def __init__(self) -> None:
        self.connection = object()
        self.committed = False
        self.rolled_back = False

    @asynccontextmanager
    async def begin(self):
        try:
            yield self.connection
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True


def context(*, roles: list[str] | None = None) -> MutationContext:
    return MutationContext(
        actor_user_id="curator",
        platform_roles=roles or [],
        request_id="req-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


def namespace_row(*, role: str | None = "ADMIN", status: str = "ACTIVE") -> dict[str, object]:
    return {
        "id": 7,
        "slug": "opensource",
        "type": "TEAM",
        "status": status,
        "namespace_role": role,
    }


def collection_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 20,
        "namespace_id": 7,
        "slug": "superpowers",
        "display_name": "Superpowers",
        "summary": "Curated skills",
        "status": "ACTIVE",
        "hidden": False,
        "latest_published_version_id": 120,
    }
    row.update(overrides)
    return row


def draft_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 121,
        "collection_id": 20,
        "version": "draft",
        "status": "DRAFT",
        "draft_revision": 2,
        "release_notes": None,
    }
    row.update(overrides)
    return row


def member_reference(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "skill_id": 80,
        "skill_version_id": 901,
        "skill_slug_snapshot": "brainstorming",
        "skill_version_snapshot": "4.1.0",
        "skill_owner_id_snapshot": "owner",
        "skill_visibility_snapshot": "PUBLIC",
        "version_skill_id": 80,
        "namespace_id": 7,
        "skill_status": "ACTIVE",
        "skill_hidden": False,
        "version_status": "PUBLISHED",
        "download_ready": True,
        "yanked_at": None,
    }
    row.update(overrides)
    return row


def repository(**overrides: object) -> SimpleNamespace:
    methods = {
        "read_namespace_for_update": AsyncMock(return_value=namespace_row()),
        "read_collection_for_update": AsyncMock(return_value=collection_row()),
        "read_collection_by_id": AsyncMock(return_value=collection_row()),
        "read_idempotency": AsyncMock(return_value=None),
        "delete_expired_idempotency": AsyncMock(),
        "reserve_idempotency": AsyncMock(return_value=True),
        "complete_idempotency": AsyncMock(),
        "insert_collection": AsyncMock(return_value=collection_row()),
        "read_draft_for_update": AsyncMock(return_value=draft_row()),
        "insert_draft": AsyncMock(return_value=draft_row(draft_revision=1)),
        "clone_members": AsyncMock(),
        "update_collection_metadata": AsyncMock(),
        "delete_draft_members": AsyncMock(),
        "read_skill_version_reference": AsyncMock(return_value=member_reference()),
        "insert_draft_member": AsyncMock(),
        "increment_draft_revision": AsyncMock(return_value=draft_row(draft_revision=3)),
        "delete_draft": AsyncMock(return_value=True),
        "read_draft_members_for_publish": AsyncMock(
            return_value=[
                {
                    **member_reference(),
                    "position": 0,
                    "note": None,
                }
            ]
        ),
        "read_latest_version_for_update": AsyncMock(
            return_value={"id": 120, "version": "1.1.0", "status": "PUBLISHED"}
        ),
        "publish_draft": AsyncMock(
            return_value={
                "id": 121,
                "collection_id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "draft_revision": 2,
            }
        ),
        "update_latest_published_version": AsyncMock(),
        "read_published_version_by_id": AsyncMock(
            return_value={
                "id": 121,
                "collection_id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
            }
        ),
        "update_collection_status": AsyncMock(return_value=collection_row(status="ARCHIVED")),
    }
    methods.update(overrides)
    return SimpleNamespace(**methods)


def test_semantic_version_implements_semver_precedence() -> None:
    assert SemanticVersion.parse("1.2.0") > SemanticVersion.parse("1.1.9")
    assert SemanticVersion.parse("1.0.0") > SemanticVersion.parse("1.0.0-rc.1")
    assert SemanticVersion.parse("1.0.0-rc.10") > SemanticVersion.parse("1.0.0-rc.2")
    assert SemanticVersion.parse("1.0.0+build.2") == SemanticVersion.parse("1.0.0+build.1")

    with pytest.raises(CollectionMutationError, match="error.collection.version.invalid"):
        SemanticVersion.parse("01.0.0")


def test_create_collection_is_idempotent_and_audited_in_transaction() -> None:
    repo = repository(read_collection_for_update=AsyncMock(return_value=None))
    audit = AsyncMock()
    engine = FakeEngine()

    result = asyncio.run(
        create_collection(
            engine,
            namespace="opensource",
            slug="superpowers",
            display_name="Superpowers",
            summary="Curated skills",
            idempotency_key="create-1",
            context=context(),
            repository=repo,
            audit_writer=audit,
        )
    )

    assert result["collectionId"] == 20
    assert engine.committed is True
    repo.reserve_idempotency.assert_awaited_once()
    repo.complete_idempotency.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "COLLECTION_CREATE"


def test_duplicate_create_returns_original_resource_without_second_insert() -> None:
    repo = repository(
        read_idempotency=AsyncMock(
            return_value={
                "request_id": "create-1",
                "resource_type": "COLLECTION_CREATE",
                "resource_id": 20,
                "status": "COMPLETED",
            }
        )
    )

    result = asyncio.run(
        create_collection(
            FakeEngine(),
            namespace="opensource",
            slug="superpowers",
            display_name="Superpowers",
            summary="Curated skills",
            idempotency_key="create-1",
            context=context(),
            repository=repo,
            audit_writer=AsyncMock(),
        )
    )

    assert result["collectionId"] == 20
    repo.insert_collection.assert_not_awaited()


def test_create_draft_clones_latest_published_members() -> None:
    repo = repository(read_draft_for_update=AsyncMock(return_value=None))
    audit = AsyncMock()

    result = asyncio.run(
        create_collection_draft(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            context=context(),
            repository=repo,
            audit_writer=audit,
        )
    )

    assert result["draftRevision"] == 1
    repo.insert_draft.assert_awaited_once()
    repo.clone_members.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "COLLECTION_DRAFT_CREATE"


def test_replace_draft_validates_all_members_before_deleting_existing_rows() -> None:
    repo = repository(
        read_skill_version_reference=AsyncMock(
            side_effect=[member_reference(), None]
        )
    )
    payload = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "releaseNotes": "Refresh",
            "members": [
                {"skillId": 80, "skillVersionId": 901, "position": 0},
                {"skillId": 81, "skillVersionId": 902, "position": 1},
            ],
        }
    )

    with pytest.raises(CollectionMutationError, match="error.collection.member.notFound"):
        asyncio.run(
            replace_collection_draft(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                payload=payload,
                expected_revision=2,
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    repo.delete_draft_members.assert_not_awaited()
    repo.update_collection_metadata.assert_not_awaited()


def test_replace_draft_replaces_members_and_increments_revision_once() -> None:
    repo = repository()
    payload = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {"skillId": 80, "skillVersionId": 901, "position": 0}
            ],
        }
    )

    result = asyncio.run(
        replace_collection_draft(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            payload=payload,
            expected_revision=2,
            context=context(),
            repository=repo,
            audit_writer=AsyncMock(),
        )
    )

    assert result["draftRevision"] == 3
    repo.delete_draft_members.assert_awaited_once()
    repo.insert_draft_member.assert_awaited_once()
    assert repo.insert_draft_member.await_args.kwargs["skill_slug_snapshot"] == "brainstorming"
    assert repo.insert_draft_member.await_args.kwargs["skill_version_snapshot"] == "4.1.0"
    assert repo.insert_draft_member.await_args.kwargs["skill_owner_id_snapshot"] == "owner"
    assert repo.insert_draft_member.await_args.kwargs["skill_visibility_snapshot"] == "PUBLIC"
    repo.increment_draft_revision.assert_awaited_once()


def test_replace_draft_preserves_exact_submitted_skill_and_version_ids() -> None:
    repo = repository(
        read_skill_version_reference=AsyncMock(
            return_value=member_reference(
                skill_id=202,
                skill_version_id=902,
                skill_slug_snapshot="duplicate-coordinate",
                skill_version_snapshot="1.0.0",
                skill_owner_id_snapshot="second-owner",
            )
        )
    )
    payload = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {
                    "skillId": 202,
                    "skillVersionId": 902,
                    "position": 0,
                }
            ],
        }
    )

    asyncio.run(
        replace_collection_draft(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            payload=payload,
            expected_revision=2,
            context=context(),
            repository=repo,
            audit_writer=AsyncMock(),
        )
    )

    repo.read_skill_version_reference.assert_awaited_once_with(
        repo.read_skill_version_reference.await_args.args[0],
        namespace_id=7,
        skill_id=202,
        skill_version_id=902,
    )
    inserted = repo.insert_draft_member.await_args.kwargs
    assert inserted["skill_id"] == 202
    assert inserted["skill_version_id"] == 902
    assert inserted["skill_slug_snapshot"] == "duplicate-coordinate"
    assert inserted["skill_owner_id_snapshot"] == "second-owner"


@pytest.mark.parametrize(
    ("skill_id", "skill_version_id"),
    [
        (202, 901),
        (303, 903),
    ],
    ids=["mismatched-skill-version", "skill-outside-collection-namespace"],
)
def test_replace_draft_rejects_unresolvable_member_ids_before_mutation(
    skill_id: int,
    skill_version_id: int,
) -> None:
    repo = repository(read_skill_version_reference=AsyncMock(return_value=None))
    payload = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {
                    "skillId": skill_id,
                    "skillVersionId": skill_version_id,
                    "position": 0,
                }
            ],
        }
    )

    with pytest.raises(
        CollectionMutationError,
        match="error.collection.member.notFound",
    ) as denied:
        asyncio.run(
            replace_collection_draft(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                payload=payload,
                expected_revision=2,
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    assert denied.value.status_code == 400
    repo.delete_draft_members.assert_not_awaited()
    repo.update_collection_metadata.assert_not_awaited()


def test_collection_draft_contract_rejects_legacy_member_coordinates() -> None:
    with pytest.raises(ValidationError):
        CollectionDraftReplaceRequest.model_validate(
            {
                "displayName": "Superpowers",
                "summary": "Curated skills",
                "members": [
                    {
                        "skillSlug": "duplicate-coordinate",
                        "version": "1.0.0",
                        "position": 0,
                    }
                ],
            }
        )


def test_collection_draft_contract_rejects_more_than_one_hundred_members() -> None:
    assert MAX_COLLECTION_MEMBERS == 100

    with pytest.raises(ValidationError):
        CollectionDraftReplaceRequest.model_validate(
            {
                "displayName": "Oversized",
                "summary": "Too many exact versions",
                "members": [
                    {
                        "skillId": index + 1,
                        "skillVersionId": index + 1001,
                        "position": index,
                    }
                    for index in range(MAX_COLLECTION_MEMBERS + 1)
                ],
            }
        )


def test_delete_draft_never_accepts_published_version_as_draft() -> None:
    repo = repository(read_draft_for_update=AsyncMock(return_value=None))

    with pytest.raises(CollectionMutationError, match="error.collection.draft.notFound"):
        asyncio.run(
            delete_collection_draft(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    repo.delete_draft.assert_not_awaited()


@pytest.mark.parametrize(
    "invalid_member",
    [
        {"namespace_id": 8},
        {"skill_status": "ARCHIVED"},
        {"skill_hidden": True},
        {"version_status": "DRAFT"},
        {"download_ready": False},
        {"yanked_at": NOW},
        {"version_skill_id": 81},
    ],
)
def test_publish_requires_installable_same_namespace_exact_versions(
    invalid_member: dict[str, object],
) -> None:
    repo = repository(
        read_draft_members_for_publish=AsyncMock(
            return_value=[{**member_reference(), **invalid_member, "position": 0}]
        )
    )

    with pytest.raises(CollectionMutationError, match="error.collection.member.invalid"):
        asyncio.run(
            publish_collection(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                payload=CollectionPublishRequest(version="1.2.0", draft_revision=2),
                idempotency_key="publish-1",
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )


def test_publish_rejects_member_whose_live_target_was_deleted() -> None:
    repo = repository(
        read_draft_members_for_publish=AsyncMock(
            return_value=[
                {
                    **member_reference(
                        skill_id=None,
                        skill_version_id=None,
                        version_skill_id=None,
                        namespace_id=None,
                        skill_status=None,
                        skill_hidden=None,
                        version_status=None,
                        download_ready=None,
                    ),
                    "position": 0,
                }
            ]
        )
    )

    with pytest.raises(CollectionMutationError, match="error.collection.member.invalid"):
        asyncio.run(
            publish_collection(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                payload=CollectionPublishRequest(version="1.2.0", draft_revision=2),
                idempotency_key="publish-deleted",
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    repo.publish_draft.assert_not_awaited()

    repo.publish_draft.assert_not_awaited()


def test_publish_updates_snapshot_latest_pointer_audit_and_idempotency() -> None:
    repo = repository()
    audit = AsyncMock()

    result = asyncio.run(
        publish_collection(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            payload=CollectionPublishRequest(version="1.2.0", draft_revision=2),
            idempotency_key="publish-1",
            context=context(),
            repository=repo,
            audit_writer=audit,
        )
    )

    assert result == {"collectionId": 20, "versionId": 121, "version": "1.2.0"}
    repo.publish_draft.assert_awaited_once()
    repo.update_latest_published_version.assert_awaited_once()
    repo.complete_idempotency.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "COLLECTION_PUBLISH"


def test_publish_rejects_non_increasing_version() -> None:
    repo = repository()

    with pytest.raises(CollectionMutationError, match="error.collection.version.notGreater"):
        asyncio.run(
            publish_collection(
                FakeEngine(),
                namespace="opensource",
                collection="superpowers",
                payload=CollectionPublishRequest(version="1.1.0", draft_revision=2),
                idempotency_key="publish-1",
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    repo.publish_draft.assert_not_awaited()


def test_archive_and_restore_use_namespace_curator_policy() -> None:
    archive_repo = repository()
    archived = asyncio.run(
        set_collection_status(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            payload=CollectionStatusRequest(status="ARCHIVED", reason="retired"),
            context=context(),
            repository=archive_repo,
            audit_writer=AsyncMock(),
        )
    )
    restore_repo = repository(
        read_collection_for_update=AsyncMock(
            return_value=collection_row(status="ARCHIVED")
        ),
        update_collection_status=AsyncMock(return_value=collection_row(status="ACTIVE")),
    )
    restored = asyncio.run(
        set_collection_status(
            FakeEngine(),
            namespace="opensource",
            collection="superpowers",
            payload=CollectionStatusRequest(status="ACTIVE"),
            context=context(),
            repository=restore_repo,
            audit_writer=AsyncMock(),
        )
    )

    assert archived["status"] == "ARCHIVED"
    assert restored["status"] == "ACTIVE"


def test_collection_mutation_routes_require_auth_and_forward_concurrency_headers() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=True)
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }
    seen: list[tuple[str, str | None, int | None]] = []

    def writer(
        action: str,
        namespace: str,
        collection: str | None,
        payload: object,
        idempotency_key: str | None,
        expected_revision: int | None,
        user: dict[str, object],
        request: object,
    ) -> dict[str, object]:
        seen.append((action, idempotency_key, expected_revision))
        if action in {"create", "status"}:
            return api_detail()
        if action == "delete_draft":
            return {"deleted": True}
        return api_version(draft=action != "publish")

    app.state.collection_mutation_writer = writer
    client = TestClient(app)
    auth = {"X-Mock-User-Id": "curator"}

    assert client.post(
        "/api/web/namespaces/opensource/collections",
        json={"slug": "superpowers", "displayName": "Superpowers", "summary": "Curated skills"},
    ).status_code == 401

    created = client.post(
        "/api/web/namespaces/opensource/collections",
        json={"slug": "superpowers", "displayName": "Superpowers", "summary": "Curated skills"},
        headers={**auth, "Idempotency-Key": "create-1"},
    )
    drafted = client.post(
        "/api/web/collections/opensource/superpowers/draft",
        headers=auth,
    )
    replaced = client.put(
        "/api/web/collections/opensource/superpowers/draft",
        json={
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {"skillId": 80, "skillVersionId": 901, "position": 0}
            ],
        },
        headers={**auth, "If-Match": '"1"'},
    )
    deleted = client.delete(
        "/api/web/collections/opensource/superpowers/draft",
        headers=auth,
    )
    published = client.post(
        "/api/web/collections/opensource/superpowers/publish",
        json={"version": "1.2.0", "draftRevision": 2},
        headers={**auth, "Idempotency-Key": "publish-1"},
    )
    archived = client.put(
        "/api/web/collections/opensource/superpowers/status",
        json={"status": "ARCHIVED", "reason": "retired"},
        headers=auth,
    )

    assert [response.status_code for response in [created, drafted, replaced, deleted, published, archived]] == [
        200,
        200,
        200,
        200,
        200,
        200,
    ]
    assert seen == [
        ("create", "create-1", None),
        ("create_draft", None, None),
        ("replace_draft", None, 1),
        ("delete_draft", None, None),
        ("publish", "publish-1", None),
        ("status", None, None),
    ]
