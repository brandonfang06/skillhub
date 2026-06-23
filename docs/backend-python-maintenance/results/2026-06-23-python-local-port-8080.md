# Python Local Port 8080 Cutover

Date: 2026-06-23

## Purpose

The Python backend no longer coexists with the removed Java backend, so local
development and frontend dev proxy defaults should use port `8080` instead of
the former hybrid-only Python port `8081`.

## Changes

- `Makefile` now starts the Python backend on `http://localhost:8080`.
- Vite dev proxy routes `/api`, `/oauth2`, `/login/oauth2`, and
  `/.well-known` to `http://localhost:8080`.
- OAuth local default `SKILLHUB_PUBLIC_BASE_URL` fallback is
  `http://localhost:8080`.
- Active local development, manual testing, and K8s port-forward docs now use
  backend `8080`.
- K8s local port-forward examples use web `3000:80` and backend `8080:8080`
  to avoid local port conflicts.

Historical migration archive files under `docs/backend-python-migration/` still
mention `8081` because they record the Java/Python coexistence period.

## Verification

Passed:

```powershell
cd server-python
uv run pytest tests/test_hybrid_makefile.py::test_makefile_defines_python_backend_process_only tests/test_python_runtime_cutover.py::test_active_python_runtime_docs_and_configs_do_not_use_hybrid_8081_port -q
```

Result: `2 passed`.

Passed:

```powershell
cd server-python
uv run pytest tests -q
```

Result: `824 passed, 1 warning`.

Passed:

```powershell
cd web
corepack pnpm exec vitest run vite.config.test.ts
```

Result: `5 passed`.

Passed:

```powershell
cd web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
```

Vitest result: `182` test files passed, `604` tests passed.

Passed:

```powershell
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

Passed with no matches:

```powershell
rg -n "8081" -S -g "!docs/backend-python-migration/**" -g "!docs/backend-python-maintenance/results/**" -g "!server-python/tests/**" -g "!web/vite.config.test.ts" .
```

Runtime smoke after stopping staging:

```powershell
docker compose -p skillhub-staging -f docker-compose.yml -f docker-compose.staging.yml down --remove-orphans
docker compose -p skillhub up -d --wait
cd server-python
uv run python -m app.migrations upgrade
$env:BOOTSTRAP_ADMIN_ENABLED='true'
$env:SKILLHUB_SECURITY_SCANNER_ENABLED='true'
$env:SKILLHUB_SECURITY_SCANNER_MODE='upload'
$env:SKILLHUB_SCAN_CONSUMER_ENABLED='true'
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Result:

- `http://localhost:8080/api/v1/health` returned
  `response.success.health` with `message=UP`.
- `Get-NetTCPConnection -LocalPort 3000,8080,8081 -State Listen` showed
  listeners on `3000` and `8080` only; `8081` had no listener.
- `corepack pnpm exec vite --host 0.0.0.0 --strictPort` served the frontend on
  `http://localhost:3000/`.
- `http://localhost:3000/api/v1/health` returned
  `response.success.health` with `message=UP`, confirming the Vite dev proxy
  routes API traffic to the Python backend on `8080`.
