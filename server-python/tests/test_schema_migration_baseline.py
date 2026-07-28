from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app import migrations


ROOT = Path(__file__).resolve().parents[2]
FLYWAY_DIR = ROOT / "server-python" / "app" / "db" / "migration"


class FakeConnection:
    def __init__(
        self,
        existing_tables: set[str] | None = None,
        existing_columns: set[tuple[str, str]] | None = None,
        fail_after_execute_containing: str | None = None,
        lock_timeout: str = "0",
    ) -> None:
        self.existing_tables = existing_tables or set()
        self.existing_columns = existing_columns or set()
        self.fail_after_execute_containing = fail_after_execute_containing
        self.lock_timeout = lock_timeout
        self.executed: list[str] = []
        self.committed: list[str] = []
        self.events: list[str] = []
        self.transaction_isolations: list[str | None] = []
        self.values: list[object] = []

    @asynccontextmanager
    async def transaction(self, *, isolation: str | None = None) -> AsyncIterator[None]:
        self.transaction_isolations.append(isolation)
        self.events.append("transaction:enter")
        transaction_start = len(self.executed)
        try:
            yield
        except BaseException:
            self.events.append("transaction:rollback")
            raise
        else:
            self.committed.extend(self.executed[transaction_start:])
            self.events.append("transaction:exit")

    async def fetchval(self, sql: str, *params: object) -> object:
        statement = sql if not params else f"{sql} {params!r}"
        self.events.append(f"fetchval:{statement}")
        self.values.append((sql, params))
        if sql == "SHOW lock_timeout":
            return self.lock_timeout
        if "to_regclass" in sql and params:
            return params[0] if params[0] in self.existing_tables else None
        if "information_schema.columns" in sql and len(params) >= 2:
            return 1 if (str(params[0]), str(params[1])) in self.existing_columns else None
        return None

    async def execute(self, sql: str, *params: object) -> str:
        statement = sql if not params else f"{sql} {params!r}"
        self.executed.append(statement)
        self.events.append(f"execute:{statement}")
        if "set_config('lock_timeout'" in sql and params:
            self.lock_timeout = str(params[0])
        if self.fail_after_execute_containing and self.fail_after_execute_containing in sql:
            raise RuntimeError("injected execute failure")
        return "OK"


def test_baseline_revision_tracks_bundled_python_migration_snapshot() -> None:
    latest_flyway = max(migrations.flyway_migration_files(FLYWAY_DIR), key=lambda item: item.version)

    assert migrations.BASELINE_FLYWAY_VERSION == latest_flyway.version
    assert migrations.BASELINE_REVISION == "skillhub_flyway_v43_baseline"
    assert latest_flyway.path.name == "V43__user_account_system_account.sql"


def test_alembic_baseline_files_are_present() -> None:
    alembic_ini = ROOT / "server-python" / "alembic.ini"
    env_py = ROOT / "server-python" / "alembic" / "env.py"
    versions_dir = ROOT / "server-python" / "alembic" / "versions"
    baseline_files = list(versions_dir.glob("*_baseline_existing_flyway_schema.py"))

    assert "script_location = alembic" in alembic_ini.read_text(encoding="utf-8")
    assert "app.migrations" in env_py.read_text(encoding="utf-8")
    assert len(baseline_files) == 1
    assert f'revision = "{migrations.BASELINE_REVISION}"' in baseline_files[0].read_text(encoding="utf-8")


def test_fresh_database_upgrade_applies_flyway_sql_then_stamps_baseline() -> None:
    connection = FakeConnection()

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert any("CREATE TABLE user_account" in statement for statement in connection.executed)
    assert any("DO $$" in statement for statement in connection.executed)
    assert any("CREATE TABLE IF NOT EXISTS alembic_version" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)


def test_fresh_upgrade_locks_before_bundled_baseline_sql() -> None:
    connection = FakeConnection()

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert connection.events[0] == "transaction:enter"
    assert connection.events.count("transaction:enter") == 1
    assert connection.transaction_isolations == ["read_committed"]
    assert "pg_advisory_xact_lock" in connection.executed[0]
    assert next(
        index
        for index, sql in enumerate(connection.executed)
        if "CREATE TABLE user_account" in sql
    ) > 0
    assert any("INSERT INTO local_schema_migration" in sql for sql in connection.executed)
    assert connection.events[-1] == "transaction:exit"


def test_direct_local_migration_application_uses_operation_transaction() -> None:
    connection = FakeConnection()

    asyncio.run(migrations.apply_local_schema_migrations(connection))

    assert connection.events[0] == "transaction:enter"
    assert connection.events.count("transaction:enter") == 1
    assert "pg_advisory_xact_lock" in connection.executed[0]
    assert any("CREATE TABLE IF NOT EXISTS local_schema_migration" in sql for sql in connection.executed)
    assert any("INSERT INTO local_schema_migration" in sql for sql in connection.executed)
    assert connection.events[-1] == "transaction:exit"


def test_local_migration_tracking_insert_failure_rolls_back_ddl(tmp_path: Path) -> None:
    identifier = "20260727_01"
    migration_sql = "CREATE TABLE rollback_probe (id INTEGER);"
    (tmp_path / f"{identifier}__rollback_probe.sql").write_text(migration_sql, encoding="utf-8")
    connection = FakeConnection(fail_after_execute_containing="INSERT INTO local_schema_migration")

    with pytest.raises(RuntimeError, match="injected execute failure"):
        asyncio.run(migrations.apply_local_schema_migrations(connection, local_dir=tmp_path))

    assert migration_sql in connection.executed
    tracking_inserts = [
        sql
        for sql in connection.executed
        if "INSERT INTO local_schema_migration" in sql and identifier in sql
    ]
    assert len(tracking_inserts) == 1
    assert connection.events[-1] == "transaction:rollback"
    assert not any(migration_sql in sql for sql in connection.committed)
    assert not any(tracking_insert in connection.committed for tracking_insert in tracking_inserts)


def test_existing_flyway_database_stamp_does_not_reapply_legacy_sql() -> None:
    connection = FakeConnection(existing_tables={"user_account"}, existing_columns={("user_account", "system_account")})

    asyncio.run(migrations.stamp_existing_database(connection))

    assert connection.events[0] == "transaction:enter"
    assert connection.events.count("transaction:enter") == 1
    assert connection.transaction_isolations == ["read_committed"]
    assert "pg_advisory_xact_lock" in connection.executed[0]
    assert connection.events[-1] == "transaction:exit"
    assert not any("CREATE TABLE user_account" in statement for statement in connection.executed)
    assert any("CREATE TABLE IF NOT EXISTS alembic_version" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)
    assert not any(
        "CREATE TABLE IF NOT EXISTS local_schema_migration" in statement
        for statement in connection.executed
    )
    assert not any("INSERT INTO local_schema_migration" in statement for statement in connection.executed)


def test_migration_status_does_not_enter_operation_transaction() -> None:
    connection = FakeConnection()

    status = asyncio.run(migrations.migration_status(connection))

    assert status == "unversioned"
    assert connection.transaction_isolations == []
    assert not any("pg_advisory_xact_lock" in statement for statement in connection.executed)


def test_existing_v42_python_database_applies_v43_before_stamping_baseline() -> None:
    connection = FakeConnection(existing_tables={"user_account"})

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert not any("CREATE TABLE user_account" in statement for statement in connection.executed)
    assert any("ADD COLUMN system_account" in statement for statement in connection.executed)
    assert any("CREATE TABLE IF NOT EXISTS alembic_version" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)


def test_fresh_upgrade_restores_lock_timeout_between_bundled_migrations(tmp_path: Path) -> None:
    v42_sql = "SET LOCAL lock_timeout = '5s';\nSELECT 'v42';"
    v43_sql = "SELECT 'v43-after-lock-timeout';"
    (tmp_path / "V42__lock_timeout.sql").write_text(v42_sql, encoding="utf-8")
    (tmp_path / "V43__after_lock_timeout.sql").write_text(v43_sql, encoding="utf-8")
    connection = FakeConnection(lock_timeout="7s")

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=tmp_path))

    v42_index = connection.executed.index(v42_sql)
    v43_index = connection.executed.index(v43_sql)
    restore_sql = "SELECT set_config('lock_timeout', $1, true)"
    restore_statements = [
        (index, statement)
        for index, statement in enumerate(connection.executed)
        if restore_sql in statement
    ]
    assert restore_statements
    first_restore_index, first_restore_statement = restore_statements[0]
    assert v42_index < first_restore_index < v43_index
    assert first_restore_statement == f"{restore_sql} ('7s',)"
    assert sum(sql == "SHOW lock_timeout" for sql, _params in connection.values) == 2


def test_local_migration_files_include_download_event_extension() -> None:
    local_migrations = migrations.local_migration_files(ROOT / "server-python" / "app" / "db" / "local_migration")

    assert any(
        item.identifier == "20260708_01"
        and item.path.name == "20260708_01__local_skill_download_event.sql"
        for item in local_migrations
    )


def test_local_migration_files_include_collection_extension() -> None:
    local_migrations = migrations.local_migration_files(ROOT / "server-python" / "app" / "db" / "local_migration")

    assert any(
        item.identifier == "20260726_01"
        and item.path.name == "20260726_01__local_collections.sql"
        for item in local_migrations
    )


def test_local_migration_files_include_repository_import_extension() -> None:
    local_migrations = migrations.local_migration_files(
        ROOT / "server-python" / "app" / "db" / "local_migration"
    )

    assert any(
        item.identifier == "20260726_02"
        and item.path.name == "20260726_02__local_repository_imports.sql"
        for item in local_migrations
    )


def test_existing_v43_python_database_applies_local_migrations_after_baseline() -> None:
    connection = FakeConnection(
        existing_tables={"user_account"},
        existing_columns={("user_account", "system_account")},
    )

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert any("CREATE TABLE IF NOT EXISTS local_schema_migration" in statement for statement in connection.executed)
    assert any("local_skill_download_event" in statement for statement in connection.executed)
    assert any("idx_local_skill_download_event_created_at" in statement for statement in connection.executed)
    assert any("local_collection_version_member" in statement for statement in connection.executed)
    assert any("idx_local_collection_namespace_status" in statement for statement in connection.executed)
    assert any("local_repository_import_candidate" in statement for statement in connection.executed)
    assert any("idx_local_repository_import_namespace_state" in statement for statement in connection.executed)
    assert any("INSERT INTO local_schema_migration" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)


def test_makefile_db_reset_uses_python_schema_migration_command() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "db-migrate-python:" in makefile
    assert "cd server-python && uv run python -m app.migrations upgrade" in makefile
    assert "cd server && ./mvnw flyway:migrate -pl skillhub-app" not in makefile


def test_pr_workflow_runs_python_schema_migration_tests() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pr-tests.yml").read_text(encoding="utf-8")

    assert "Server Python Tests" in workflow
    assert "uv run pytest tests -q" in workflow


def test_schema_migration_takeover_is_recorded_in_cutover_docs() -> None:
    final_plan = (
        ROOT / "docs" / "backend-python-migration" / "plans" / "2026-06-12-final-python-cutover.md"
    ).read_text(encoding="utf-8")
    sequence = (ROOT / "docs" / "backend-python-migration" / "migration-sequence-plan.md").read_text(
        encoding="utf-8"
    )
    result = (
        ROOT
        / "docs"
        / "backend-python-migration"
        / "results"
        / "2026-06-12-python-schema-migration-takeover.md"
    ).read_text(encoding="utf-8")

    assert "| 119 | Python schema migration takeover | python |" in sequence
    assert "- [x] Python schema migrations initialize fresh DBs and stamp/upgrade existing DBs." in final_plan
    assert "uv run python -m app.migrations upgrade" in result
    assert "uv run python -m app.migrations stamp" in result
