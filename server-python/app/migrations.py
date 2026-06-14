from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import asyncpg

from app.core.config import get_settings


BASELINE_FLYWAY_VERSION = 42
BASELINE_REVISION = "skillhub_flyway_v42_baseline"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLYWAY_DIR = ROOT / "server-python" / "app" / "db" / "migration"


class DatabaseConnection(Protocol):
    async def fetchval(self, sql: str, *params: object) -> object: ...

    async def execute(self, sql: str, *params: object) -> str: ...


@dataclass(frozen=True)
class FlywayMigration:
    version: int
    description: str
    path: Path


def flyway_migration_files(flyway_dir: Path = DEFAULT_FLYWAY_DIR) -> list[FlywayMigration]:
    migrations: list[FlywayMigration] = []
    for path in flyway_dir.glob("V*__*.sql"):
        prefix, description = path.name.split("__", 1)
        if not prefix[1:].isdigit():
            continue
        migrations.append(
            FlywayMigration(
                version=int(prefix[1:]),
                description=description.removesuffix(".sql"),
                path=path,
            )
        )
    return sorted(migrations, key=lambda item: item.version)


async def table_exists(connection: DatabaseConnection, table_name: str) -> bool:
    value = await connection.fetchval("SELECT to_regclass($1)", table_name)
    return value is not None


async def stamp_existing_database(connection: DatabaseConnection) -> None:
    if not await table_exists(connection, "user_account"):
        raise RuntimeError("Cannot stamp baseline: expected existing Flyway table user_account")
    await _stamp_baseline(connection)


async def upgrade_database(
    connection: DatabaseConnection,
    flyway_dir: Path = DEFAULT_FLYWAY_DIR,
) -> None:
    if await table_exists(connection, "user_account"):
        await _stamp_baseline(connection)
        return

    migrations = flyway_migration_files(flyway_dir)
    if not migrations or migrations[-1].version != BASELINE_FLYWAY_VERSION:
        raise RuntimeError(
            f"Baseline expects Flyway V{BASELINE_FLYWAY_VERSION}, "
            f"found V{migrations[-1].version if migrations else 'none'}"
        )

    for migration in migrations:
        await connection.execute(migration.path.read_text(encoding="utf-8"))
    await _stamp_baseline(connection)


async def migration_status(connection: DatabaseConnection) -> str:
    if not await table_exists(connection, "alembic_version"):
        return "unversioned"
    current = await connection.fetchval("SELECT version_num FROM alembic_version LIMIT 1")
    return str(current) if current is not None else "unversioned"


async def _stamp_baseline(connection: DatabaseConnection) -> None:
    await connection.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) PRIMARY KEY)")
    await connection.execute("DELETE FROM alembic_version")
    await connection.execute("INSERT INTO alembic_version (version_num) VALUES ($1)", BASELINE_REVISION)


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _run_with_connection(action: str) -> str:
    connection = await asyncpg.connect(_asyncpg_url(get_settings().database_url))
    try:
        if action == "upgrade":
            await upgrade_database(connection)
            return BASELINE_REVISION
        if action == "stamp":
            await stamp_existing_database(connection)
            return BASELINE_REVISION
        if action == "status":
            return await migration_status(connection)
        raise ValueError(f"Unsupported migration action: {action}")
    finally:
        await connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SkillHub Python schema migration command")
    parser.add_argument("action", choices=["upgrade", "stamp", "status"])
    args = parser.parse_args(argv)

    result = asyncio.run(_run_with_connection(args.action))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
