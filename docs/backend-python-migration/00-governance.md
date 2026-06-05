# Backend Python Migration Governance

This document defines the rules for gradually replacing Java backend endpoints
with a Python FastAPI backend while both services run side by side.

## Absolute Java Boundary

- Never edit, move, delete, format, regenerate, or otherwise mutate files under
  `server/`.
- Treat `server/` as the read-only reference implementation.
- Reading Java code, running Java tests, and starting the Java server for
  comparison are allowed.
- If a migration appears to require a Java change, stop and record the blocker
  in the session result. Do not work around it by editing Java.

## Runtime Boundary

- Java backend remains on `http://localhost:8080`.
- Python FastAPI backend runs on `http://localhost:8081`.
- Vite dev proxy routes Python-owned API paths to port `8081`.
- All non-migrated `/api` paths and `/oauth2` continue to route to Java on
  port `8080`.

## Route Ownership

- Each route has exactly one active owner: `java` or `python`.
- Route ownership must be recorded in `route-registry.md`.
- Changing route ownership must include a plan, implementation, verification,
  result document, commit, and push.
- Vite proxy config must be updated whenever local development ownership
  changes.

## Python Backend Rules

- Python backend code lives under `server-python/`.
- Use Python 3.12, FastAPI, `uv`, and `server-python/.venv`.
- Commit `pyproject.toml` and `uv.lock`.
- Never commit `.venv`.
- PostgreSQL schema remains owned by Java Flyway during coexistence.
- Python must not create or modify schema unless a future governance change
  explicitly allows it.

## API Contract Rules

- Preserve the Java API response envelope:

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
- Preserve Java status codes, field names, pagination shapes, and file/download
  exceptions for migrated endpoints.
- Mutating endpoints may not move to Python until equivalent idempotency behavior
  is implemented.
- Auth, session, OAuth, and API token behavior remain Java-owned until a written
  bridge plan is approved.

## Required Session Records

Every implementation session must create or update:

- `docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md`
- `docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md`
- `docs/backend-python-migration/route-registry.md`

Each result must include:

- routes changed
- owner before and after
- files changed
- tests run and exact outcome
- boundary check proving `server/` was not changed
- known risks
- follow-up work

