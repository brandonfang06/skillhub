# server-python AGENTS.md

This directory contains the FastAPI backend that gradually replaces selected
Java `server/` endpoints during the Java/Python coexistence period.

## Mission

- Implement Python-owned API routes with the same external contract as the
  existing Java backend.
- Keep Java `server/` and Python `server-python/` running side by side during
  migration.
- Preserve frontend behavior: migrated routes go to `localhost:8081`;
  non-migrated routes stay on Java `localhost:8080`.

## Absolute Java Boundary

- Never edit, move, delete, format, or regenerate any file under `server/`.
- Treat `server/` as read-only reference implementation.
- You may read Java code, run Java tests, and start the Java server for
  comparison.
- You may not change Java controllers, services, domain models, repositories,
  configs, tests, Maven files, Dockerfiles, scripts, or Flyway migrations.
- If a migration appears to require Java changes, stop and document the blocker
  in the session result. Do not work around it by editing Java.

## Hard Boundaries

- Do not migrate an endpoint unless it is listed in
  `docs/backend-python-migration/route-registry.md`.
- Do not change database schema from Python during coexistence. Java Flyway
  remains the schema owner.
- Do not implement auth/session/OAuth/API-token behavior unless a written
  migration plan explicitly covers it.
- Do not migrate mutating endpoints until Python has equivalent `X-Request-Id`
  idempotency behavior.
- Do not edit generated frontend API types manually.

## Python Tooling

- Use Python 3.12.
- Use `uv` for dependency and virtual environment management.
- Virtual env path: `server-python/.venv`.
- Commit `pyproject.toml` and `uv.lock`.
- Never commit `.venv`.

Common commands:

```powershell
cd server-python
uv venv .venv
uv sync
uv run pytest
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

Dependency changes must use:

```powershell
uv add <package>
uv remove <package>
```

Record every dependency change in the session result document.

## API Contract Rules

- JSON responses must use the SkillHub envelope:

```json
{
  "code": 0,
  "msg": "success",
  "data": {},
  "timestamp": "2026-06-06T00:00:00Z",
  "requestId": "..."
}
```

- Reuse incoming `X-Request-Id`; generate one when missing.
- Return `X-Request-Id` in response headers.
- Preserve Java status codes, response shapes, pagination fields, and
  file/download exceptions.
- Do not introduce Python-only response formats.

## Route Ownership

Every endpoint migration must update:

- `docs/backend-python-migration/route-registry.md`
- `web/vite.config.ts`
- the related session plan under `docs/backend-python-migration/plans/`
- the related session result under `docs/backend-python-migration/results/`

A route must have exactly one active owner: `java` or `python`.

## Architecture

Prefer small modules with clear boundaries:

- `app/main.py`: FastAPI app factory and router registration
- `app/api/`: route handlers
- `app/core/`: config, request id middleware, response envelope helpers
- `app/db/`: SQLAlchemy engine/session setup
- `app/repositories/`: database queries
- `app/services/`: business workflow orchestration
- `app/schemas/`: Pydantic request/response models
- `tests/`: pytest tests

Route handlers should stay thin: bind request data, call services, return
envelope responses.

## Testing Requirements

Every change needs tests before or alongside implementation.

Minimum checks per migrated endpoint:

- Python route test with `pytest`
- response envelope test
- request id propagation test
- contract comparison against Java behavior when practical
- Vite proxy ownership test or config assertion when route ownership changes

Before marking a session complete, run:

```powershell
cd server-python
uv run pytest
```

If frontend proxy changed, also run the relevant web test/typecheck command from
`web/`.

## Session Documentation

Before implementation, write a plan in:

```text
docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md
```

After implementation, write a result in:

```text
docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md
```

Each result must include:

- routes changed
- owner before/after
- files changed
- tests run and exact outcome
- known risks
- follow-up work

