from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.collections.contracts import CollectionDraftReplaceRequest, CollectionPublishRequest
from app.collections.service import (
    CollectionMutationError,
    create_collection,
    publish_collection,
    replace_collection_draft,
)
from tests.test_collection_mutations import (
    FakeEngine,
    collection_row,
    context,
    draft_row,
    repository,
)


def test_create_rolls_back_when_audit_write_fails() -> None:
    repo = repository(read_collection_for_update=AsyncMock(return_value=None))
    engine = FakeEngine()
    audit = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        asyncio.run(
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

    assert engine.rolled_back is True
    assert engine.committed is False
    repo.complete_idempotency.assert_not_awaited()


def test_stale_if_match_leaves_draft_members_unchanged() -> None:
    repo = repository(read_draft_for_update=AsyncMock(return_value=draft_row(draft_revision=3)))
    payload = CollectionDraftReplaceRequest.model_validate(
        {
            "displayName": "Superpowers",
            "summary": "Curated skills",
            "members": [
                {"skillId": 80, "skillVersionId": 901, "position": 0}
            ],
        }
    )

    with pytest.raises(CollectionMutationError, match="error.collection.draft.stale"):
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
    repo.insert_draft_member.assert_not_awaited()
    repo.increment_draft_revision.assert_not_awaited()


def test_publish_rolls_back_status_latest_audit_and_idempotency_on_failure() -> None:
    repo = repository(
        update_latest_published_version=AsyncMock(side_effect=RuntimeError("latest failed"))
    )
    engine = FakeEngine()

    with pytest.raises(RuntimeError, match="latest failed"):
        asyncio.run(
            publish_collection(
                engine,
                namespace="opensource",
                collection="superpowers",
                payload=CollectionPublishRequest(version="1.2.0", draft_revision=2),
                idempotency_key="publish-1",
                context=context(),
                repository=repo,
                audit_writer=AsyncMock(),
            )
        )

    assert engine.rolled_back is True
    repo.publish_draft.assert_awaited_once()
    repo.complete_idempotency.assert_not_awaited()


def test_duplicate_publish_returns_original_published_version() -> None:
    repo = repository(
        read_idempotency=AsyncMock(
            return_value={
                "request_id": "publish-1",
                "resource_type": "COLLECTION_PUBLISH",
                "resource_id": 121,
                "status": "COMPLETED",
            }
        )
    )

    result = asyncio.run(
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

    assert result == {"collectionId": 20, "versionId": 121, "version": "1.2.0"}
    repo.publish_draft.assert_not_awaited()
    repo.update_latest_published_version.assert_not_awaited()


def test_duplicate_create_key_for_another_collection_is_conflict() -> None:
    repo = repository(
        read_idempotency=AsyncMock(
            return_value={
                "request_id": "create-1",
                "resource_type": "COLLECTION_CREATE",
                "resource_id": 20,
                "status": "COMPLETED",
            }
        ),
        read_collection_by_id=AsyncMock(return_value=collection_row(slug="other")),
    )

    with pytest.raises(CollectionMutationError, match="error.collection.idempotency.conflict"):
        asyncio.run(
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
