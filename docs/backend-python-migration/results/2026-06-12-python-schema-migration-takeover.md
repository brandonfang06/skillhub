# Python Schema Migration Takeover Result

Date: 2026-06-12

Milestone: 119 - Python Schema Migration Takeover

## Summary

Python now owns the final cutover schema migration path. `server-python` has an Alembic baseline
marker at `skillhub_flyway_v43_baseline` and a Python migration command:

```powershell
uv run python -m app.migrations upgrade
uv run python -m app.migrations stamp
uv run python -m app.migrations status
```

`upgrade` initializes a fresh database by applying the existing Java Flyway SQL files in numeric
order through `V43__user_account_system_account.sql`, then stamps the Alembic version table.
Existing Python databases created from the earlier v42 baseline apply the V43 compatibility
migration before being stamped as v43, so `user_account.system_account` exists before the
current runtime starts using it. `stamp` marks an existing Flyway-created schema without replaying
legacy SQL. Java Flyway files under `server/` were not modified.

## Dependency Change

Added `alembic` to `server-python/pyproject.toml` through `uv add alembic`; `uv.lock` was updated.

## Files

- `server-python/app/migrations.py`
- `server-python/alembic.ini`
- `server-python/alembic/env.py`
- `server-python/alembic/versions/20260612_baseline_existing_flyway_schema.py`
- `server-python/tests/test_schema_migration_baseline.py`
- `Makefile`
- `.github/workflows/pr-tests.yml`
- `server-python/README.md`
- `server-python/AGENTS.md`

## Fresh Database Verification

Verified against a temporary local Postgres database named `skillhub_migration_119`:

```powershell
$env:SKILLHUB_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub_migration_119"
uv run python -m app.migrations upgrade
```

Observed:

- `alembic_version.version_num = skillhub_flyway_v43_baseline`
- `to_regclass('user_account') = user_account`
- `to_regclass('skill') = skill`
- `to_regclass('notification') = notification`

## Existing Schema Stamp Verification

After dropping only `alembic_version` from the same initialized temporary database:

```powershell
$env:SKILLHUB_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub_migration_119"
uv run python -m app.migrations stamp
```

Observed:

- `alembic_version.version_num = skillhub_flyway_v43_baseline`
- existing tables remained intact
- legacy Flyway SQL was not replayed

The temporary database was dropped after verification.

## Local Workflow

`make db-migrate-python` runs:

```powershell
cd server-python && uv run python -m app.migrations upgrade
```

`make db-reset` now starts Postgres and delegates to `make db-migrate-python`.
This removes the local reset path's dependency on `cd server && ./mvnw flyway:migrate -pl
skillhub-app`.

## CI Validation

`.github/workflows/pr-tests.yml` now includes a `Server Python Tests` job that installs Python 3.12,
installs `uv`, and runs:

```powershell
cd server-python && uv run pytest tests/test_schema_migration_baseline.py
```

## Verification

- `uv run pytest tests/test_schema_migration_baseline.py -q`
- `uv run pytest tests/test_schema_migration_baseline.py tests/test_final_cutover_baseline.py tests/test_hybrid_makefile.py -q`
- `uv run pytest tests -q`
- temporary fresh database `upgrade`
- temporary existing schema `stamp`
- CI workflow static coverage through `tests/test_schema_migration_baseline.py`
- `git diff --name-only -- server`

Full-suite verification also exposed two stale test assumptions unrelated to schema migration:

- `POST /api/v1/skills` is now Python-owned by the publish router, so the empty request returns
  FastAPI validation `422` instead of the old unowned-route `405`.
- `tests/test_publish_transaction.py` fake SQL results now model `.mappings().all()` for the
  pending-review auto-withdraw query.
