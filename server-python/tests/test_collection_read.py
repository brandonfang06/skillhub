from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.collections.read_repository import CollectionReadError, get_collection, list_collections
from app.main import create_app


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


class Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def mappings(self) -> "Result":
        return self

    def one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return list(self.value)


class ScriptedConnection:
    def __init__(self, results: list[Any]) -> None:
        self.results = list(results)
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
        self.statements.append(str(statement))
        return Result(self.results.pop(0))


class FakeEngine:
    def __init__(self, connection: ScriptedConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def connect(self):
        yield self.connection


def namespace_row(*, role: str | None = None) -> dict[str, Any]:
    return {
        "id": 7,
        "slug": "opensource",
        "type": "TEAM",
        "status": "ACTIVE",
        "namespace_role": role,
    }


def collection_row(
    *,
    status: str = "ACTIVE",
    hidden: bool = False,
    visibility: str = "PUBLIC",
) -> dict[str, Any]:
    return {
        "id": 20,
        "namespace": "opensource",
        "slug": "superpowers",
        "display_name": "Superpowers",
        "summary": "Curated skills",
        "status": status,
        "hidden": hidden,
        "created_at": NOW,
        "updated_at": NOW,
        "latest_version_id": 120,
        "latest_version": "1.2.0",
        "latest_status": "PUBLISHED",
        "latest_draft_revision": 2,
        "latest_release_notes": "Release",
        "latest_created_at": NOW,
        "latest_published_at": NOW,
        "latest_member_count": 1,
        "draft_version_id": 121,
        "draft_version": "draft",
        "draft_status": "DRAFT",
        "draft_revision": 1,
        "draft_release_notes": None,
        "draft_created_at": NOW,
        "draft_published_at": None,
        "draft_member_count": 1,
        "_visibility": visibility,
    }


def member_row(
    *,
    collection_version_id: int,
    visibility: str = "PUBLIC",
) -> dict[str, Any]:
    return {
        "collection_version_id": collection_version_id,
        "skill_id": 80,
        "skill_version_id": 901,
        "version_skill_id": 80,
        "namespace": "opensource",
        "skill_slug": "brainstorming",
        "version": "4.1.0",
        "position": 0,
        "note": None,
        "owner_id": "owner",
        "visibility": visibility,
        "latest_version_id": 901,
        "skill_status": "ACTIVE",
        "skill_hidden": False,
        "version_status": "PUBLISHED",
        "download_ready": True,
        "yanked_at": None,
    }


def deleted_member_row(
    *,
    collection_version_id: int = 120,
    visibility: str = "PUBLIC",
    owner_id: str = "owner",
) -> dict[str, Any]:
    return {
        "collection_version_id": collection_version_id,
        "skill_id": None,
        "skill_version_id": None,
        "version_skill_id": None,
        "namespace": "opensource",
        "skill_slug": "brainstorming",
        "version": "4.1.0",
        "position": 0,
        "note": "Historical member",
        "owner_id": owner_id,
        "visibility": visibility,
        "latest_version_id": 901,
        "skill_status": None,
        "skill_hidden": None,
        "version_status": None,
        "download_ready": None,
        "yanked_at": None,
    }


def test_list_filters_inaccessible_published_snapshots_for_non_curators() -> None:
    public = collection_row()
    private = {**collection_row(), "id": 21, "slug": "private", "latest_version_id": 220}
    connection = ScriptedConnection(
        [
            namespace_row(role=None),
            [public, private],
            [
                member_row(collection_version_id=120),
                {**member_row(collection_version_id=220, visibility="PRIVATE"), "skill_id": 81},
            ],
        ]
    )

    data = asyncio.run(
        list_collections(
            FakeEngine(connection),
            namespace="opensource",
            current_user_id=None,
            platform_roles=[],
        )
    )

    assert data["total"] == 1
    assert [item["slug"] for item in data["items"]] == ["superpowers"]
    assert data["items"][0]["draft"] is None


def test_curator_list_includes_archived_collection_and_draft() -> None:
    archived = collection_row(status="ARCHIVED")
    connection = ScriptedConnection(
        [
            namespace_row(role="ADMIN"),
            [archived],
            [
                member_row(collection_version_id=120, visibility="PRIVATE"),
                member_row(collection_version_id=121, visibility="PRIVATE"),
            ],
        ]
    )

    data = asyncio.run(
        list_collections(
            FakeEngine(connection),
            namespace="opensource",
            current_user_id="admin",
            platform_roles=[],
        )
    )

    assert data["total"] == 1
    assert data["items"][0]["canCurate"] is True
    assert data["items"][0]["status"] == "ARCHIVED"
    assert data["items"][0]["draft"]["draftRevision"] == 1


def test_detail_returns_exact_latest_and_draft_members_for_curator() -> None:
    connection = ScriptedConnection(
        [
            namespace_row(role="OWNER"),
            collection_row(),
            [
                member_row(collection_version_id=120),
                {**member_row(collection_version_id=121), "skill_version_id": 902, "version": "4.2.0"},
            ],
        ]
    )

    data = asyncio.run(
        get_collection(
            FakeEngine(connection),
            namespace="opensource",
            collection="superpowers",
            current_user_id="owner",
            platform_roles=[],
        )
    )

    assert data["latestPublishedVersion"]["members"][0]["version"] == "4.1.0"
    assert data["draft"]["members"][0]["version"] == "4.2.0"
    assert data["canCurate"] is True


def test_detail_retains_snapshot_and_nullable_ids_after_target_deletion() -> None:
    connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [deleted_member_row()],
        ]
    )

    data = asyncio.run(
        get_collection(
            FakeEngine(connection),
            namespace="opensource",
            collection="superpowers",
            current_user_id=None,
            platform_roles=[],
        )
    )

    member = data["latestPublishedVersion"]["members"][0]
    assert member == {
        "skillId": None,
        "skillVersionId": None,
        "namespace": "opensource",
        "skillSlug": "brainstorming",
        "version": "4.1.0",
        "position": 0,
        "note": "Historical member",
    }
    member_query = connection.statements[2].lower()
    assert "left join skill s" in member_query
    assert "left join skill_version sv" in member_query
    assert "skill_slug_snapshot" in member_query
    assert "skill_version_snapshot" in member_query


def test_deleted_namespace_only_history_keeps_namespace_membership_boundary() -> None:
    hidden_connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [deleted_member_row(visibility="NAMESPACE_ONLY")],
        ]
    )

    with pytest.raises(CollectionReadError, match="error.collection.notFound"):
        asyncio.run(
            get_collection(
                FakeEngine(hidden_connection),
                namespace="opensource",
                collection="superpowers",
                current_user_id=None,
                platform_roles=[],
            )
        )

    member_connection = ScriptedConnection(
        [
            namespace_row(role="MEMBER"),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [deleted_member_row(visibility="NAMESPACE_ONLY")],
        ]
    )
    data = asyncio.run(
        get_collection(
            FakeEngine(member_connection),
            namespace="opensource",
            collection="superpowers",
            current_user_id="member",
            platform_roles=[],
        )
    )

    assert data["latestPublishedVersion"]["members"][0]["skillId"] is None


def test_deleted_private_history_keeps_owner_boundary() -> None:
    anonymous_connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [deleted_member_row(visibility="PRIVATE")],
        ]
    )
    with pytest.raises(CollectionReadError, match="error.collection.notFound"):
        asyncio.run(
            get_collection(
                FakeEngine(anonymous_connection),
                namespace="opensource",
                collection="superpowers",
                current_user_id=None,
                platform_roles=[],
            )
        )

    owner_connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [deleted_member_row(visibility="PRIVATE", owner_id="owner")],
        ]
    )
    data = asyncio.run(
        get_collection(
            FakeEngine(owner_connection),
            namespace="opensource",
            collection="superpowers",
            current_user_id="owner",
            platform_roles=[],
        )
    )

    assert data["latestPublishedVersion"]["members"][0]["skillVersionId"] is None


def test_detail_retains_snapshot_when_only_public_version_target_is_deleted() -> None:
    connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [
                member_row(
                    collection_version_id=120,
                )
                | {
                    "skill_version_id": None,
                    "version_skill_id": None,
                    "version_status": None,
                    "download_ready": None,
                }
            ],
        ]
    )

    data = asyncio.run(
        get_collection(
            FakeEngine(connection),
            namespace="opensource",
            collection="superpowers",
            current_user_id=None,
            platform_roles=[],
        )
    )

    member = data["latestPublishedVersion"]["members"][0]
    assert member["skillId"] == 80
    assert member["skillVersionId"] is None
    assert member["skillSlug"] == "brainstorming"
    assert member["version"] == "4.1.0"


@pytest.mark.parametrize(
    "surviving_skill_state",
    [
        {"visibility": "PRIVATE"},
        {"skill_status": "ARCHIVED"},
        {"skill_hidden": True},
        {
            "skill_id": None,
            "skill_version_id": 901,
            "version_skill_id": 80,
            "owner_id": None,
            "visibility": None,
            "skill_status": None,
            "skill_hidden": None,
            "version_status": "PUBLISHED",
            "download_ready": True,
        },
    ],
)
def test_detail_does_not_bypass_live_skill_access_for_partial_reference(
    surviving_skill_state: dict[str, Any],
) -> None:
    partially_deleted = {
        **member_row(collection_version_id=120),
        "skill_version_id": None,
        "version_skill_id": None,
        "version_status": None,
        "download_ready": None,
        **surviving_skill_state,
    }
    connection = ScriptedConnection(
        [
            namespace_row(role=None),
            {**collection_row(), "draft_version_id": None, "draft_member_count": 0},
            [partially_deleted],
        ]
    )

    with pytest.raises(CollectionReadError, match="error.collection.notFound"):
        asyncio.run(
            get_collection(
                FakeEngine(connection),
                namespace="opensource",
                collection="superpowers",
                current_user_id=None,
                platform_roles=[],
            )
        )


def test_detail_hides_inaccessible_collection_as_not_found() -> None:
    connection = ScriptedConnection(
        [
            namespace_row(role=None),
            collection_row(),
            [member_row(collection_version_id=120, visibility="PRIVATE")],
        ]
    )

    with pytest.raises(CollectionReadError, match="error.collection.notFound") as missing:
        asyncio.run(
            get_collection(
                FakeEngine(connection),
                namespace="opensource",
                collection="superpowers",
                current_user_id=None,
                platform_roles=[],
            )
        )

    assert missing.value.status_code == 404


def api_version(*, draft: bool = False) -> dict[str, Any]:
    return {
        "versionId": 121 if draft else 120,
        "version": "draft" if draft else "1.2.0",
        "status": "DRAFT" if draft else "PUBLISHED",
        "draftRevision": 1 if draft else 2,
        "memberCount": 1,
        "releaseNotes": None,
        "createdAt": "2026-07-27T08:00:00Z",
        "publishedAt": None if draft else "2026-07-27T08:00:00Z",
        "members": [
            {
                "skillId": 80,
                "skillVersionId": 901,
                "namespace": "opensource",
                "skillSlug": "brainstorming",
                "version": "4.1.0",
                "position": 0,
                "note": None,
            }
        ],
    }


def api_detail() -> dict[str, Any]:
    return {
        "collectionId": 20,
        "namespace": "opensource",
        "slug": "superpowers",
        "displayName": "Superpowers",
        "summary": "Curated skills",
        "status": "ACTIVE",
        "hidden": False,
        "canCurate": True,
        "latestPublishedVersion": api_version(),
        "draft": api_version(draft=True),
        "createdAt": "2026-07-27T08:00:00Z",
        "updatedAt": "2026-07-27T08:00:00Z",
    }


def test_collection_read_routes_return_typed_envelopes() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=True)

    def reader(
        action: str,
        namespace: str,
        collection: str | None,
        current_user_id: str | None,
        platform_roles: list[str],
    ) -> dict[str, Any]:
        assert namespace == "opensource"
        if action == "list":
            summary = {key: value for key, value in api_detail().items()}
            summary["latestPublishedVersion"] = {
                key: value for key, value in api_version().items() if key != "members"
            }
            summary["draft"] = {
                key: value for key, value in api_version(draft=True).items() if key != "members"
            }
            return {"items": [summary], "total": 1}
        assert collection == "superpowers"
        return api_detail()

    app.state.collection_reader = reader
    client = TestClient(app)

    listed = client.get(
        "/api/web/namespaces/opensource/collections",
        headers={"X-Request-Id": "collection-list"},
    )
    detail = client.get(
        "/api/web/collections/opensource/superpowers",
        headers={"X-Request-Id": "collection-detail"},
    )

    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["requestId"] == "collection-list"
    assert detail.status_code == 200
    assert detail.json()["data"]["draft"]["draftRevision"] == 1
    assert detail.json()["requestId"] == "collection-detail"


def test_collection_detail_contract_accepts_null_historical_member_ids() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=True)
    historical = api_detail()
    historical["latestPublishedVersion"]["members"][0]["skillId"] = None
    historical["latestPublishedVersion"]["members"][0]["skillVersionId"] = None
    app.state.collection_reader = (
        lambda action, namespace, collection, current_user_id, platform_roles: historical
    )

    response = TestClient(app).get(
        "/api/web/collections/opensource/superpowers",
        headers={"X-Request-Id": "historical-collection-detail"},
    )

    assert response.status_code == 200
    member = response.json()["data"]["latestPublishedVersion"]["members"][0]
    assert member["skillId"] is None
    assert member["skillVersionId"] is None
