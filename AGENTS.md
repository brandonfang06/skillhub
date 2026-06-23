# AGENTS.md

Universal coding agent instructions for Brandon's SkillHub workspace.

## Current Runtime

SkillHub is now a full-Python backend project. The old Java `server/` directory
has been removed on this branch.

| Component | Location | Notes |
| --- | --- | --- |
| Backend | `server-python/` | FastAPI, SQLAlchemy async, Alembic/bundled SQL baseline, Python 3.12, `uv` |
| Frontend | `web/` | React, TypeScript, Vite, pnpm |
| Scanner | `scanner/` | Python scanner container |
| CLI | `cli/` | TypeScript/Bun CLI |
| K8s | `deploy/k8s/` | Deploys frontend, backend-python, scanner only |

PostgreSQL, Redis, MinIO/S3, and Keycloak/OIDC are external services in
organization deployments. Local Docker compose remains available for home/dev
testing.

## Quick Rules

- Write tests before or alongside code changes.
- Verify each phase before starting the next.
- Persist plans/results under `docs/`; do not leave design decisions only in
  chat.
- Prefer small, direct changes that match the existing Python/TypeScript code.
- Do not reintroduce Java, Maven, Spring Boot, or a hybrid Java/Python runtime.
- Do not manually edit generated files.

## Backend Rules

- Backend code lives in `server-python/app`.
- Backend tests live in `server-python/tests`.
- Schema baseline SQL lives in `server-python/app/db/migration`.
- Future schema work must be Python-owned and covered by tests.
- New SQL must live in repository/query/helper modules, not route handlers.
- ORM models require a milestone plan and targeted transaction tests.
- Mutating endpoint changes need authorization, audit actor, idempotency,
  transaction, and rollback/compensation coverage.

Common commands:

```powershell
cd server-python
uv sync --frozen
uv run pytest tests -q
uv run python -m app.migrations upgrade
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Frontend Rules

- Use generated OpenAPI types from `web/src/api/generated/`.
- Do not fetch server data with `useEffect`; use TanStack Query patterns.
- Keep Feature-Sliced Design placement: pages, features, entities, shared.
- Run `pnpm run typecheck`, `pnpm run lint`, and relevant tests for UI changes.

## Deployment

- Release/runtime backend image is `ghcr.io/iflytek/skillhub-server-python`.
- K8s manifests deploy only `skillhub-web`, `skillhub-server`, and
  `skillhub-scanner`.
- Full K8s env documentation is in
  `deploy/k8s/environment-variables.zh.md`.
- Local release compose can run PostgreSQL, Redis, MinIO, backend, scanner, and
  web for verification.

## Documentation Source Of Truth

- Post-cutover backend hardening: `docs/backend-python-maintenance/`.
- Historical Java-to-Python migration archive: `docs/backend-python-migration/`.
- Deployment/operator docs: `deploy/k8s/`.
- Product/user docs: `docs/skillhub/`, `document/`, and `web/src/docs/`.

## Git And Verification

- Default development branch is `dev`; use feature branches for scoped work.
- Commit subjects should be imperative and under 72 characters.
- Before claiming completion, run the relevant tests and record the exact
  commands/results.
- For broad backend/deployment changes, run at minimum:

```powershell
cd server-python
uv run pytest tests -q
cd ..
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```
