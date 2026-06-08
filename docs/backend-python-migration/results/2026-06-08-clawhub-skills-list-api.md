# ClawHub Skills List API Result

Date: 2026-06-08

## Summary

Migrated `GET /api/v1/skills` to FastAPI as the remaining Group A ClawHub public catalog read
route.

The route returns plain ClawHub JSON, not the SkillHub `ApiResponse` envelope. Vite uses
method-aware routing so only `GET /api/v1/skills` reaches Python. Root publish
`POST /api/v1/skills` remains Java-owned.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills` | java | python |

## Routes Kept Java-Owned

| Method | Path | Owner |
| --- | --- | --- |
| POST | `/api/v1/skills` | java |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java |
| GET | `/api/v1/download/{canonicalSlug}` | java |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/download` | java |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/file` | java |

## Implementation Notes

- Added `build_clawhub_skills_list_response` to map the existing public skill search response into
  Java-compatible ClawHub list shape.
- Added `GET /api/v1/skills` route in FastAPI.
- Reused `read_skill_search` with empty keyword, no namespace, no labels, and requested sort/page
  parameters.
- Added Vite method-aware GET-only ownership for `/api/v1/skills`.
- Kept root `POST /api/v1/skills` and same-path mutations on Java fallback.
- Added Windows live gate `verify-clawhub-list-smoke`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result: `95 passed, 1 warning`.

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `15 passed`.

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
```

Result: exit code `0`.

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-list-smoke
```

Result:

```text
allJavaMatchesPython: true
allPythonMatchesProxy: true
plainShape: true
rootPostRemainsJava: true
deleteRemainsJava: true
downloadRemainsJava: true
Playwright smoke: 6 passed
```

The latest contract result is written to:

```text
.dev/clawhub-list-contract-result.json
```

## Risks And Follow-Up

- Group A public catalog reads are now Python-owned except routes intentionally kept Java-owned for
  publish, mutation, and download behavior.
- The next migration group should be selected from the revised pre-launch roadmap:
  - Group B file content and download read path, or
  - Group C auth/current user bridge.
- Do not migrate root `POST /api/v1/skills` without the publish/upload vertical slice plan.
- Do not migrate download/file content routes without the storage and download behavior bridge
  plan.
