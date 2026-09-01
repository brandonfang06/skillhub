# SkillHub Python Backend

FastAPI backend for the full-Python SkillHub runtime.

## Local Development

```powershell
uv venv .venv
uv sync
uv run pytest
uv run python -m app.migrations upgrade
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Schema Migrations

Python owns the final cutover schema path through:

```powershell
uv run python -m app.migrations upgrade
uv run python -m app.migrations stamp
uv run python -m app.migrations status
```

`upgrade` initializes a fresh database from the bundled SQL baseline in
`app/db/migration` and stamps the Alembic baseline revision. `stamp` marks an
existing baseline schema without replaying legacy SQL.

Back up PostgreSQL and package object storage before every production upgrade.
The v0.2.18 baseline adds V44/V45 `scan_task_outbox` migrations. After upgrade,
run `status`, confirm existing skill/version rows remain intact, and verify a
scanner-enabled publish reaches `scan_task_outbox.status = 'SENT'` before the
consumer completes the task. Organization-only schema continues under
`app/db/local_migration`; do not reuse upstream `V*` numbers for local tables.
