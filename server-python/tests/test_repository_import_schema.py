from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "server-python"
    / "app"
    / "db"
    / "local_migration"
    / "20260726_02__local_repository_imports.sql"
)


def normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_repository_import_schema_is_additive_and_secret_free() -> None:
    sql = normalized_sql()

    assert "create table if not exists local_repository_import (" in sql
    assert "create table if not exists local_repository_import_candidate (" in sql
    assert "gitlab_token" not in sql
    assert "access_token" not in sql
    assert "raw_response" not in sql


def test_repository_import_schema_locks_provenance_and_retry_identity() -> None:
    sql = normalized_sql()

    assert "resolved_commit_sha char(40) not null" in sql
    assert "archive_sha256 char(64) not null" in sql
    assert "unique (import_id, source_path)" in sql
    assert "previous_import_id bigint references local_repository_import(id)" in sql
    assert "ingest_operation_id varchar(64)" in sql
    assert "skill_id bigint references skill(id) on delete set null" in sql
    assert (
        "skill_version_id bigint references skill_version(id) on delete set null"
        in sql
    )
    assert "check (state in ('preview_ready', 'ingesting', 'completed', 'partial', 'failed'))" in sql
    assert "check (state in ('discovered', 'selected', 'created', 'failed'))" in sql


def test_repository_import_schema_has_query_indexes() -> None:
    sql = normalized_sql()

    assert "idx_local_repository_import_namespace_state" in sql
    assert "idx_local_repository_import_project_ref" in sql
    assert "idx_local_repository_import_candidate_state" in sql
    assert (
        "create index if not exists "
        "idx_local_repository_import_candidate_skill_id "
        "on local_repository_import_candidate(skill_id) "
        "where skill_id is not null"
    ) in sql
    assert (
        "create index if not exists "
        "idx_local_repository_import_candidate_skill_version_id "
        "on local_repository_import_candidate(skill_version_id) "
        "where skill_version_id is not null"
    ) in sql
