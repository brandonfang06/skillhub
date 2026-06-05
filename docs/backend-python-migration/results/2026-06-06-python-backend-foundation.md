# Python Backend Foundation Result

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | Java on `localhost:8080` | Python on `localhost:8081` |

All other `/api/**` routes remain Java-owned. `/oauth2/**` remains Java-owned.

## Files Changed

- Added migration governance docs under `docs/backend-python-migration/`.
- Added FastAPI foundation under `server-python/`.
- Added `server-python/AGENTS.md` with the absolute Java boundary.
- Added Python health tests under `server-python/tests/`.
- Added Vite proxy ownership test at `web/vite.config.test.ts`.
- Updated `web/vite.config.ts` to route `/api/v1/health` to port `8081`
  before the Java `/api` fallback.

## Tests Run

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Outcome: 2 tests passed, 1 warning from FastAPI/Starlette TestClient.

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv sync
```

Outcome: resolved 29 packages and checked 27 packages.

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Outcome: 1 test file passed, 2 tests passed.

## Boundary Check

`git diff --name-only` showed no tracked changes under `server/`.

`git status --short` showed no untracked files under `server/`.

## Known Risks

- Python currently owns only `GET /api/v1/health`; no database, auth, session,
  API token, idempotency, or file streaming behavior has been migrated.
- Frontend `pnpm exec` did not resolve the Vitest shim in this PowerShell
  environment, so verification used the direct `.CMD` shim.
- `uv` default cache path had local permission issues, so verification used
  `UV_CACHE_DIR=.uv-cache`.

## Follow-Up Work

- Add a Makefile target or documented command for starting Python on port 8081.
- Pick the first real public GET API group for migration after reviewing route
  complexity and contract risk.
- Decide when staging/release routing should learn Python-owned routes.

