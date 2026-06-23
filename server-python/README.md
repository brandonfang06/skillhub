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
