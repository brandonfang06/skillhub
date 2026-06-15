from __future__ import annotations

import asyncio
from pathlib import Path

from app import migrations


ROOT = Path(__file__).resolve().parents[2]
FLYWAY_DIR = ROOT / "server-python" / "app" / "db" / "migration"


class FakeConnection:
    def __init__(self, existing_tables: set[str] | None = None, existing_columns: set[tuple[str, str]] | None = None) -> None:
        self.existing_tables = existing_tables or set()
        self.existing_columns = existing_columns or set()
        self.executed: list[str] = []
        self.values: list[object] = []

    async def fetchval(self, sql: str, *params: object) -> object:
        self.values.append((sql, params))
        if "to_regclass" in sql and params:
            return params[0] if params[0] in self.existing_tables else None
        if "information_schema.columns" in sql and len(params) >= 2:
            return 1 if (str(params[0]), str(params[1])) in self.existing_columns else None
        return None

    async def execute(self, sql: str, *params: object) -> str:
        self.executed.append(sql if not params else f"{sql} {params!r}")
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


def test_existing_flyway_database_stamp_does_not_reapply_legacy_sql() -> None:
    connection = FakeConnection(existing_tables={"user_account"}, existing_columns={("user_account", "system_account")})

    asyncio.run(migrations.stamp_existing_database(connection))

    assert not any("CREATE TABLE user_account" in statement for statement in connection.executed)
    assert any("CREATE TABLE IF NOT EXISTS alembic_version" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)


def test_existing_v42_python_database_applies_v43_before_stamping_baseline() -> None:
    connection = FakeConnection(existing_tables={"user_account"})

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert not any("CREATE TABLE user_account" in statement for statement in connection.executed)
    assert any("ADD COLUMN system_account" in statement for statement in connection.executed)
    assert any("CREATE TABLE IF NOT EXISTS alembic_version" in statement for statement in connection.executed)
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
