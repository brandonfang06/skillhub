# ClawHub Search API Result

Date: 2026-06-08

## Summary

Migrated `GET /api/v1/search` ClawHub compatibility search to FastAPI.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/search` | Java `localhost:8080` | Python `localhost:8081` |

Routes intentionally unchanged:

| Method | Route | Owner | Reason |
| --- | --- | --- | --- |
| GET | `/api/v1/skills` | Java | ClawHub compatibility list. |
| POST | `/api/v1/skills` | Java | ClawHub compatibility publish. |
| GET | `/api/v1/resolve` | Java | ClawHub compatibility resolve. |
| GET | `/api/v1/download/**` | Java | Download and redirect behavior remains deferred. |

## Implementation

- Added FastAPI `GET /api/v1/search`.
- Reused the anonymous public PostgreSQL search reader from portal search.
- Added ClawHub plain response mapping:
  - `slug`: `global` maps to plain slug; non-global namespace maps to `{namespace}--{slug}`.
  - `version`: published version string.
  - `score`: `(starCount * 10 + downloadCount) / 100.0`.
  - `updatedAt`: epoch milliseconds.
- Added Vite proxy ownership for `/api/v1/search`.
- Added Windows live gate `verify-clawhub-search-smoke`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_search.py tests/test_clawhub_search_repository.py tests/test_hybrid_makefile.py -v

cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-search-smoke
```

Live gate result:

```json
{
  "query": "?q=codex-search-alpha-unique&page=0&limit=5",
  "javaMatchesPython": true,
  "pythonMatchesProxy": true,
  "v1SkillsRemainsJava": true,
  "resultCount": 1,
  "firstSlug": "codex-search-alpha-20260607233000",
  "plainShape": true
}
```

The live gate also ran frontend Playwright smoke E2E: `6 passed`.

## Boundary Check

- `server/` remained read-only.
- No Java source, config, migration, generated DTO, or Java test file was changed.
- `web/src/api/generated/schema.d.ts` was not edited.

## Risks And Follow-Up

- This milestone covers anonymous public ClawHub search only.
- ClawHub list (`GET /api/v1/skills`) remains Java-owned because the same path also owns
  `POST /api/v1/skills`.
- ClawHub resolve and download routes remain Java-owned until separate plans cover their bridge
  and storage/download behavior.
