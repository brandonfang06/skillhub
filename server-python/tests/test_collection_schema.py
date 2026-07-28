from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "server-python"
    / "app"
    / "db"
    / "local_migration"
    / "20260726_01__local_collections.sql"
)


def _normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_collection_schema_uses_only_local_tables() -> None:
    sql = _normalized_sql()

    assert "create table if not exists local_collection (" in sql
    assert "create table if not exists local_collection_version (" in sql
    assert "create table if not exists local_collection_version_member (" in sql
    assert "create table collection (" not in sql
    assert "create table collection_version (" not in sql


def test_collection_schema_locks_lifecycle_and_identity_invariants() -> None:
    sql = _normalized_sql()

    assert "unique (namespace_id, slug)" in sql
    assert "check (status in ('active', 'archived'))" in sql
    assert "check (status in ('draft', 'published', 'yanked'))" in sql
    assert "unique (collection_id, version)" in sql
    assert (
        "create unique index if not exists uq_local_collection_version_one_draft "
        "on local_collection_version(collection_id) where status = 'draft'"
    ) in sql
    assert "id bigserial primary key" in sql
    assert "unique (collection_version_id, skill_version_id)" in sql
    assert "unique (collection_version_id, position)" in sql
    assert "check (position >= 0)" in sql


def test_collection_schema_has_exact_member_and_latest_version_references() -> None:
    sql = _normalized_sql()

    assert "namespace_id bigint not null references namespace(id)" in sql
    assert "skill_id bigint references skill(id) on delete set null" in sql
    assert (
        "skill_version_id bigint references skill_version(id) on delete set null"
        in sql
    )
    assert "skill_slug_snapshot varchar(128) not null" in sql
    assert "skill_version_snapshot varchar(64) not null" in sql
    assert "skill_owner_id_snapshot varchar(128) not null" in sql
    assert "skill_visibility_snapshot varchar(32) not null" in sql
    assert (
        "add constraint fk_local_collection_latest_published_version "
        "foreign key (latest_published_version_id) references local_collection_version(id)"
    ) in sql


def test_collection_schema_has_required_lookup_indexes() -> None:
    sql = _normalized_sql()

    assert "idx_local_collection_namespace_status" in sql
    assert "idx_local_collection_version_collection_status" in sql
    assert "idx_local_collection_member_skill_version" in sql
    assert (
        "create index if not exists idx_local_collection_member_skill_id "
        "on local_collection_version_member(skill_id) "
        "where skill_id is not null"
    ) in sql


def test_collection_schema_captures_final_access_policy_before_skill_delete() -> None:
    sql = _normalized_sql()

    assert (
        "create or replace function "
        "local_snapshot_collection_member_access_before_skill_delete()"
    ) in sql
    assert "skill_owner_id_snapshot = old.owner_id" in sql
    assert "skill_visibility_snapshot = old.visibility" in sql
    assert "where skill_id = old.id" in sql
    assert (
        "create trigger trg_local_collection_member_access_before_skill_delete "
        "before delete on skill"
    ) in sql
