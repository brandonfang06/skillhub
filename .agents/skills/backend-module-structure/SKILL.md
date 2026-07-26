---
name: backend-module-structure
description: Rules for placing SkillHub Python backend code in the FastAPI application without crossing route, workflow, repository, or infrastructure boundaries.
license: Apache-2.0
---

# Backend Module Structure Skill

## Trigger

Use this skill when adding or moving Python backend routes, workflows,
repositories, integrations, migrations, or tests.

## Runtime Boundary

The active backend is `server-python/`, using Python 3.12, FastAPI, async
SQLAlchemy, and `uv`. New backend work must not create another runtime or place
backend code outside `server-python/`.

## Placement

| Concern | Location |
| --- | --- |
| FastAPI route and request binding | `server-python/app/api/` |
| Feature workflow or business rule | `server-python/app/<feature>/` |
| SQL repository or read model | `server-python/app/<feature>/*repository.py` |
| Authentication and authorization | `server-python/app/auth/` |
| Audit writing | `server-python/app/audit/` |
| Shared configuration and infrastructure | `server-python/app/core/` |
| Database session and unit of work | `server-python/app/db/` |
| Bundled schema baseline | `server-python/app/db/migration/` |
| Backend tests | `server-python/tests/` |

Follow the existing feature packages such as `namespace`, `publish`, `review`,
`skills`, and `governance` instead of creating a generic service directory.

## Dependency Direction

- Route modules bind HTTP inputs, resolve auth context, call a workflow or
  repository, and shape the response.
- Business rules belong in focused feature modules and must not depend on
  FastAPI request or response objects.
- SQL belongs in repository, query, or helper modules, not route handlers.
- Storage, scanner, Redis, notification, and identity-provider calls stay
  behind their existing integration boundaries.
- Shared infrastructure may be imported by feature modules; shared
  infrastructure must not import feature workflows.

Existing route-level SQL is temporary compatibility code. Do not expand it;
keep the architecture allowlist in
`server-python/tests/test_post_cutover_architecture.py` narrow.

## Schema And Mutations

- Schema changes use the Python-owned migration path and require a milestone
  plan plus targeted migration tests.
- New ORM models require explicit transaction coverage.
- Mutating endpoints require authorization, audit actor, idempotency,
  transaction, and rollback or compensation tests.
- User identities remain strings across API, database, auth, and audit
  boundaries.

## Commands

```powershell
cd server-python
uv sync --frozen
uv run pytest tests -q
uv run python -m app.migrations upgrade
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
