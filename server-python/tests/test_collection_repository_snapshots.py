from __future__ import annotations

import asyncio
from typing import Any

from app.collections.mutation_repository import CollectionMutationRepository


class Result:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def mappings(self) -> "Result":
        return self

    def one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return list(self.value)


class RecordingConnection:
    def __init__(self, result: Any = None) -> None:
        self.result = result
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
    ) -> Result:
        self.statements.append(str(statement))
        self.params.append(dict(params or {}))
        return Result(self.result)


def test_clone_members_copies_immutable_skill_snapshots() -> None:
    connection = RecordingConnection()

    asyncio.run(
        CollectionMutationRepository().clone_members(
            connection,
            source_version_id=10,
            target_version_id=11,
        )
    )

    sql = " ".join(connection.statements[0].lower().split())
    assert "skill_slug_snapshot" in sql
    assert "skill_version_snapshot" in sql
    assert "skill_owner_id_snapshot" in sql
    assert "skill_visibility_snapshot" in sql
    assert "order by position asc, id asc" in sql


def test_reference_reads_canonical_snapshot_values_and_insert_persists_them() -> None:
    reference = {
        "skill_id": 80,
        "skill_version_id": 901,
        "skill_slug_snapshot": "canonical-slug",
        "skill_version_snapshot": "4.1.0",
        "skill_owner_id_snapshot": "owner",
        "skill_visibility_snapshot": "NAMESPACE_ONLY",
    }
    read_connection = RecordingConnection(reference)
    repository = CollectionMutationRepository()

    result = asyncio.run(
        repository.read_skill_version_reference(
            read_connection,
            namespace_id=7,
            skill_id=202,
            skill_version_id=902,
        )
    )

    assert result == reference
    read_sql = " ".join(read_connection.statements[0].lower().split())
    assert "s.slug as skill_slug_snapshot" in read_sql
    assert "sv.version as skill_version_snapshot" in read_sql
    assert "s.owner_id as skill_owner_id_snapshot" in read_sql
    assert "s.visibility as skill_visibility_snapshot" in read_sql
    assert "where s.id = :skill_id" in read_sql
    assert "and sv.id = :skill_version_id" in read_sql
    assert "and sv.skill_id = s.id" in read_sql
    assert "and s.namespace_id = :namespace_id" in read_sql
    assert "and s.status = 'active'" in read_sql
    assert "and s.hidden = false" in read_sql
    assert "and sv.status = 'published'" in read_sql
    assert "and sv.download_ready = true" in read_sql
    assert "and sv.yanked_at is null" in read_sql
    assert "order by s.id" not in read_sql
    assert "for key share of s, sv" in read_sql
    assert read_connection.params[0] == {
        "namespace_id": 7,
        "skill_id": 202,
        "skill_version_id": 902,
    }

    insert_connection = RecordingConnection()
    asyncio.run(
        repository.insert_draft_member(
            insert_connection,
            draft_id=121,
            skill_id=80,
            skill_version_id=901,
            skill_slug_snapshot="canonical-slug",
            skill_version_snapshot="4.1.0",
            skill_owner_id_snapshot="owner",
            skill_visibility_snapshot="NAMESPACE_ONLY",
            position=0,
            note=None,
        )
    )

    insert_sql = " ".join(insert_connection.statements[0].lower().split())
    assert "skill_slug_snapshot" in insert_sql
    assert "skill_version_snapshot" in insert_sql
    assert "skill_owner_id_snapshot" in insert_sql
    assert "skill_visibility_snapshot" in insert_sql
    assert insert_connection.params[0]["skill_slug_snapshot"] == "canonical-slug"
    assert insert_connection.params[0]["skill_version_snapshot"] == "4.1.0"
    assert insert_connection.params[0]["skill_owner_id_snapshot"] == "owner"
    assert (
        insert_connection.params[0]["skill_visibility_snapshot"]
        == "NAMESPACE_ONLY"
    )


def test_publish_member_query_preserves_rows_with_deleted_targets() -> None:
    connection = RecordingConnection([])

    asyncio.run(
        CollectionMutationRepository().read_draft_members_for_publish(
            connection,
            121,
        )
    )

    sql = " ".join(connection.statements[0].lower().split())
    assert "left join skill s" in sql
    assert "left join skill_version sv" in sql
    assert "for update of member" in sql
