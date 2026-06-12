# Java Runtime Deprecation And Staging Cutover Result

Date: 2026-06-12

Milestone: 120 - Java Runtime Deprecation And Staging Cutover

## Summary

Default local and staging runtime paths now use the Python backend without starting or building the
Java backend.

- `make dev-all` starts dependency services, runs Python schema migrations, starts `server-python`,
  starts the Vite frontend, and verifies `http://localhost:3000/api/v1/health` reaches Python.
- `make dev-server` and `make dev-server-restart` now target `server-python`.
- `make staging` builds `server-python/Dockerfile` as `skillhub-server-python:staging`, starts
  dependencies, runs the Python backend as the `server` compose service on port 8080, and keeps the
  web upstream as `http://server:8080`.
- The staging smoke script now targets Python health and Prometheus-compatible metrics endpoints.
- The Python backend now seeds the Java-compatible bootstrap admin account when
  `BOOTSTRAP_ADMIN_ENABLED=true`, so staging admin smoke flows do not depend on Java.
- Python local auth, namespace listing, and admin label routes now accept the session principal
  needed by the staging smoke flow instead of requiring Java/mock-only behavior.
- Java backend runtime remains available only through explicit reference/hybrid workflows such as
  `scripts/dev-hybrid.ps1`, not through default local or staging startup.

## Files

- `Makefile`
- `docker-compose.staging.yml`
- `server-python/Dockerfile`
- `scripts/smoke-test.sh`
- `server-python/app/api/admin_labels.py`
- `server-python/app/api/health.py`
- `server-python/app/api/local_auth.py`
- `server-python/app/api/namespaces.py`
- `server-python/app/bootstrap.py`
- `server-python/app/main.py`
- `server-python/tests/test_admin_label_definitions.py`
- `server-python/tests/test_bootstrap_admin.py`
- `server-python/tests/test_health.py`
- `server-python/tests/test_local_auth_core.py`
- `server-python/tests/test_namespace_read.py`
- `server-python/tests/test_python_runtime_cutover.py`
- `server-python/tests/test_session_auth.py`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`

## Verification

Completed verification for this milestone:

- `uv run pytest tests/test_python_runtime_cutover.py tests/test_namespace_read.py tests/test_admin_label_definitions.py tests/test_session_auth.py tests/test_local_auth_core.py -q`
- `uv run pytest tests -q` (`704 passed`)
- Python-only local live gate equivalent to `make dev-all`:
  - `docker compose -p skillhub up -d --wait --remove-orphans postgres redis`
  - `uv run python -m app.migrations upgrade`
  - `uv run uvicorn app.main:app --host 0.0.0.0 --port 8081`
  - `web/node_modules/.bin/vite.CMD --host 0.0.0.0 --strictPort`
  - `GET http://127.0.0.1:3000/api/v1/health` returned `200` with Python health envelope.
  - `GET http://127.0.0.1:8081/api/v1/metrics/prometheus` returned `200`.
- Staging equivalent to `make staging`:
  - `docker build -t skillhub-server-python:staging -f server-python/Dockerfile .`
  - `npm.cmd run build`
  - `docker compose -p skillhub-staging -f docker-compose.yml -f docker-compose.staging.yml up -d --wait server web`
  - `scripts/smoke-test.sh http://localhost:8080` returned `14 passed, 0 failed`.
- `git diff --name-only -- server` returned no files.

`make` and `pnpm` were not available in the current PowerShell environment, so the local and staging
runtime gates were executed with the equivalent underlying commands.

## Remaining Cutover Note

This closes Java runtime usage from default local and staging paths. The final cutover checklist
still tracks global route-policy enforcement outside the completed high-risk foundation slice as a
separate non-runtime item.
