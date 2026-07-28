from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.collections.read_repository import CollectionReadError, resolve_collection
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
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
        self.statements.append(str(statement))
        self.params.append(dict(params or {}))
        return Result(self.results.pop(0))


class FakeEngine:
    def __init__(self, connection: ScriptedConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def begin(self):
        yield self.connection


def namespace_row(*, role: str | None = None) -> dict[str, Any]:
    return {
        "id": 7,
        "slug": "opensource",
        "type": "TEAM",
        "status": "ACTIVE",
        "namespace_role": role,
    }


def version_row(*, collection_status: str = "ACTIVE", hidden: bool = False) -> dict[str, Any]:
    return {
        "collection_id": 20,
        "namespace": "opensource",
        "collection_slug": "superpowers",
        "collection_status": collection_status,
        "collection_hidden": hidden,
        "version_id": 120,
        "version": "1.2.0",
        "version_status": "PUBLISHED",
    }


def member_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "collection_version_id": 120,
        "skill_id": 80,
        "skill_version_id": 901,
        "version_skill_id": 80,
        "namespace": "opensource",
        "skill_slug": "brainstorming",
        "version": "4.1.0",
        "position": 0,
        "note": None,
        "owner_id": "owner",
        "visibility": "PUBLIC",
        "latest_version_id": 901,
        "skill_status": "ACTIVE",
        "skill_hidden": False,
        "version_status": "PUBLISHED",
        "download_ready": True,
        "yanked_at": None,
    }
    row.update(overrides)
    return row


def file_rows() -> list[dict[str, Any]]:
    return [
        {"version_id": 901, "file_path": "SKILL.md", "sha256": "a" * 64},
        {"version_id": 901, "file_path": "references/guide.md", "sha256": "b" * 64},
    ]


def test_resolve_returns_exact_deterministic_member_manifest() -> None:
    connection = ScriptedConnection(
        [namespace_row(), version_row(), [member_row()], file_rows()]
    )

    data = asyncio.run(
        resolve_collection(
            FakeEngine(connection),
            namespace="opensource",
            collection="superpowers",
            version="1.2.0",
            current_user_id=None,
            platform_roles=[],
        )
    )

    assert data["namespace"] == "opensource"
    assert data["version"] == "1.2.0"
    assert data["members"] == [
        {
            "namespace": "opensource",
            "slug": "brainstorming",
            "version": "4.1.0",
            "versionId": 901,
            "fingerprint": "sha256:20ebe7d2375d2bf6c5a7ffc4d623e96ae207934663655010c0b2d22f8582cf7e",
            "downloadUrl": "/api/cli/v1/skills/opensource/brainstorming/versions/4.1.0/download",
        }
    ]
    assert connection.params[1]["version"] == "1.2.0"


def test_resolve_without_version_uses_latest_pointer_query() -> None:
    connection = ScriptedConnection(
        [namespace_row(), version_row(), [member_row()], file_rows()]
    )

    asyncio.run(
        resolve_collection(
            FakeEngine(connection),
            namespace="opensource",
            collection="superpowers",
            version=None,
            current_user_id=None,
            platform_roles=[],
        )
    )

    assert connection.params[1]["version"] is None
    assert "latest_published_version_id" in connection.statements[1]
    assert "CAST(:version AS varchar)" in connection.statements[1]


@pytest.mark.parametrize(
    "degraded",
    [
        {"skill_status": "ARCHIVED"},
        {"skill_hidden": True},
        {"version_status": "YANKED"},
        {"download_ready": False},
        {"yanked_at": NOW},
        {"visibility": "PRIVATE"},
        {"version_skill_id": 81},
    ],
)
def test_resolve_rejects_degraded_member_without_latest_fallback(
    degraded: dict[str, Any],
) -> None:
    connection = ScriptedConnection(
        [namespace_row(), version_row(), [member_row(**degraded)]]
    )

    with pytest.raises(
        CollectionReadError,
        match="error.collection.resolve.degraded",
    ) as conflict:
        asyncio.run(
            resolve_collection(
                FakeEngine(connection),
                namespace="opensource",
                collection="superpowers",
                version="1.2.0",
                current_user_id=None,
                platform_roles=[],
            )
        )

    assert conflict.value.status_code == 409
    assert all("latest_version_id" not in sql or "local_collection" in sql for sql in connection.statements)
    assert all("FROM skill_file" not in sql for sql in connection.statements)


def test_resolve_rejects_collection_without_members_as_degraded() -> None:
    connection = ScriptedConnection([namespace_row(), version_row(), []])

    with pytest.raises(
        CollectionReadError,
        match="error.collection.resolve.degraded",
    ):
        asyncio.run(
            resolve_collection(
                FakeEngine(connection),
                namespace="opensource",
                collection="superpowers",
                version=None,
                current_user_id=None,
                platform_roles=[],
            )
        )

    assert len(connection.statements) == 3
    assert all("FROM skill_file" not in sql for sql in connection.statements)


def test_resolve_rejects_deleted_member_before_file_read() -> None:
    connection = ScriptedConnection(
        [
            namespace_row(),
            version_row(),
            [member_row(skill_id=None, skill_version_id=None, version_skill_id=None)],
        ]
    )

    with pytest.raises(
        CollectionReadError,
        match="error.collection.resolve.degraded",
    ) as conflict:
        asyncio.run(
            resolve_collection(
                FakeEngine(connection),
                namespace="opensource",
                collection="superpowers",
                version="1.2.0",
                current_user_id=None,
                platform_roles=[],
            )
        )

    assert conflict.value.status_code == 409
    assert len(connection.statements) == 3
    assert all("FROM skill_file" not in sql for sql in connection.statements)


def test_collection_cli_resolve_route_returns_exact_enveloped_contract() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(collections_enabled=True)
    app.state.collection_resolver = (
        lambda namespace, collection, version, current_user_id, platform_roles: {
            "namespace": namespace,
            "slug": collection,
            "version": version or "1.2.0",
            "versionId": 120,
            "members": [
                {
                    "namespace": namespace,
                    "slug": "brainstorming",
                    "version": "4.1.0",
                    "versionId": 901,
                    "fingerprint": "sha256:abc",
                    "downloadUrl": (
                        "/api/cli/v1/skills/opensource/brainstorming/"
                        "versions/4.1.0/download"
                    ),
                }
            ],
        }
    )
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/collections/opensource/superpowers/resolve?version=1.2.0",
        headers={"X-Request-Id": "collection-resolve"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["members"][0]["versionId"] == 901
    assert response.json()["requestId"] == "collection-resolve"
