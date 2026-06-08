# ClawHub Resolve API Result

Date: 2026-06-08

## Summary

Migrated ClawHub compatibility resolve routes to FastAPI:

- `GET /api/v1/resolve`
- `GET /api/v1/resolve/{canonicalSlug}`

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/resolve` | Java `localhost:8080` | Python `localhost:8081` |
| GET | `/api/v1/resolve/{canonicalSlug}` | Java `localhost:8080` | Python `localhost:8081` |

Routes intentionally unchanged:

| Method | Route | Owner | Reason |
| --- | --- | --- | --- |
| GET | `/api/v1/download` | Java | Download redirect and metrics remain deferred. |
| GET | `/api/v1/download/{canonicalSlug}` | Java | Download redirect and metrics remain deferred. |
| GET | `/api/v1/skills` | Java | ClawHub compatibility list and publish path remain Java-owned. |
| POST | `/api/v1/skills` | Java | Publish is mutating and auth-sensitive. |
| GET | `/api/v1/skills/{canonicalSlug}` | Java | ClawHub skill detail needs a separate plan. |

## Implementation

- Added canonical slug parsing for ClawHub compatibility:
  - `demo` -> namespace `global`, slug `demo`.
  - `team-ai--demo` -> namespace `team-ai`, slug `demo`.
  - split occurs only on the first `--`.
- Added plain ClawHub resolve response mapping:
  - `match`: `{"version": "..."}`.
  - `latestVersion`: `{"version": "..."}`.
- Added `GET /api/v1/resolve` query route.
- Added `GET /api/v1/resolve/{canonicalSlug}` path route.
- Added anonymous public legacy slug lookup for query-form resolve.
- Added exact Vite proxy ownership for the two resolve routes only.
- Added Windows live gate `verify-clawhub-resolve-smoke`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_resolve.py tests/test_clawhub_resolve_repository.py tests/test_hybrid_makefile.py -v

cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-resolve-smoke
```

Live gate result:

```json
{
  "slug": "codex-search-alpha-20260607233000",
  "query": {
    "javaMatchesPython": true,
    "pythonMatchesProxy": true,
    "matchVersion": "1.0.0",
    "latestVersion": "1.0.0"
  },
  "path": {
    "javaMatchesPython": true,
    "pythonMatchesProxy": true,
    "matchVersion": "1.0.0",
    "latestVersion": "1.0.0"
  },
  "plainShape": true,
  "downloadRemainsJava": true,
  "v1SkillDetailRemainsJava": true
}
```

The live gate also ran frontend Playwright smoke E2E: `6 passed`.

## Boundary Check

- `server/` remained read-only.
- No Java source, config, migration, generated DTO, or Java test file was changed.
- `web/src/api/generated/schema.d.ts` was not edited.

## Risks And Follow-Up

- This milestone covers anonymous public ClawHub resolve behavior only.
- Query-form legacy slug lookup is implemented for public visible skills; auth-specific access is
  still deferred until the auth/session bridge is designed.
- Download routes remain Java-owned.
- ClawHub skill detail (`GET /api/v1/skills/{canonicalSlug}`) remains Java-owned and should be
  planned as a separate milestone if selected next.
