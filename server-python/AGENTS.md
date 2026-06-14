# server-python AGENTS.md

This directory is the primary SkillHub backend. The Java `server/` reference
runtime has been removed on the full-Python branch, so new backend work must
land in `server-python/`.

## Mission

- Keep the FastAPI backend production-ready for the self-hosted SkillHub
  runtime.
- Preserve the public REST, ClawHub compatibility, auth, storage, scanner, and
  deployment contracts already migrated to Python.
- Treat `docs/backend-python-maintenance/` as the source of truth for
  post-cutover hardening plans and results.
- Keep historical migration docs under `docs/backend-python-migration/` as
  archive/reference material. Do not reopen Java route ownership milestones.

## Hard Boundaries

- Do not reintroduce a Java backend runtime, Maven build, Spring Boot image, or
  hybrid Java/Python local workflow.
- Database schema ownership is Python-only. Baseline SQL lives under
  `server-python/app/db/migration`, and future schema work must be planned as
  Python migration work.
- Do not edit generated frontend API types manually.
- Mutating endpoint changes require tests for authorization, idempotency,
  transaction boundary handling, and rollback/compensation behavior.

## Python Tooling

- Use Python 3.12.
- Use `uv` for dependency and virtual environment management.
- Virtual env path: `server-python/.venv`.
- Commit `pyproject.toml` and `uv.lock` together when dependencies change.
- Keep tests under `server-python/tests/`.

Common commands:

```powershell
cd server-python
uv sync --frozen
uv run pytest tests -q
uv run python -m app.migrations upgrade
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

## Post-Cutover Maintenance Rules

- New SQL must live in repository/query/helper modules, not new route handlers.
- ORM models require a milestone plan and targeted transaction tests before
  being introduced.
- Projection-heavy SQL can remain explicit SQL when it is isolated behind a
  repository/query/helper boundary and covered by tests.
- Existing API route SQL bridge code is temporary. Keep the allowlist in
  `server-python/tests/test_post_cutover_architecture.py` narrow and reduce it
  as repository extraction milestones complete.
- Run `uv run python scripts/sql_inventory.py` before and after broad
  repository or ORM refactors.
- Before each hardening milestone batch, fetch the canonical upstream and run
  `scripts/check-upstream-backend-drift.ps1`. Triage upstream behavior, schema,
  API contract, security, auth, lifecycle, publish/review, and data-integrity
  changes before continuing local-only refactors.

## Testing Requirements

Every backend change needs tests before or alongside implementation.

Minimum checks for a backend route or workflow change:

- Python route/service test with `pytest`.
- Response envelope and request-id behavior when the transport surface changes.
- Authorization/session/API-token behavior tests for protected routes.
- Transaction and audit actor tests for writes.
- Storage, scanner, notification, and side-effect tests when those boundaries
  are touched.

Before marking a backend session complete, run:

```powershell
cd server-python
uv run pytest tests -q
```

For deployment or container changes, also render/build the affected deployment
artifact, for example:

```powershell
docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
```

## Documentation

- Plans/results for post-cutover backend hardening belong under
  `docs/backend-python-maintenance/`.
- K8s/operator environment variable docs live under `deploy/k8s/`.
- Historical Java migration evidence remains under
  `docs/backend-python-migration/`; keep it immutable unless a correction is
  needed for auditability.
