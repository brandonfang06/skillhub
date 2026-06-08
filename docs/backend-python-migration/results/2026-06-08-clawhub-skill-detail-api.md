# ClawHub Skill Detail API Result

Date: 2026-06-08

## Summary

Migrated `GET /api/v1/skills/{canonicalSlug}` to FastAPI as a ClawHub compatibility route.

The route returns plain ClawHub JSON, not the SkillHub `ApiResponse` envelope. Vite uses
method-aware routing so only `GET` on the one-segment canonical skill path reaches Python.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{canonicalSlug}` | java | python |

## Routes Kept Java-Owned

| Method | Path | Owner |
| --- | --- | --- |
| GET | `/api/v1/skills` | java |
| POST | `/api/v1/skills` | java |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java |
| GET | `/api/v1/download/{canonicalSlug}` | java |

Nested SkillHub public routes remain on their existing Python ownership, for example
`GET /api/v1/skills/{namespace}/{slug}`.

## Implementation Notes

- Added `read_clawhub_skill_detail` so the ClawHub response can include Java-compatible
  `createdAt`, `updatedAt`, `publishedAt`, and `changelog` fields without changing portal skill
  detail response shape.
- Added `build_clawhub_skill_detail_response` for the plain compatibility response.
- Enabled Vite method-aware proxy rule for `GET /api/v1/skills/{canonicalSlug}`.
- Kept mutation methods on the same path on Java fallback.
- Updated the nested Vite skill-detail regex so `POST /api/v1/skills/{canonicalSlug}/undelete`
  cannot be captured by the two-segment public skill detail proxy.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result: `87 passed, 1 warning`.

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-skill-smoke
```

Result:

```text
javaMatchesPython: true
pythonMatchesProxy: true
plainShape: true
v1SkillsListRemainsJava: true
downloadRemainsJava: true
deleteRemainsJava: true
undeleteRemainsJava: true
Playwright smoke: 6 passed
```

The latest contract result is written to:

```text
.dev/clawhub-skill-contract-result.json
```

## Root Cause Found During Live Gate

The first live comparison failed because Python returned `skill.createdAt = 0`. Java maps this from
`skill.created_at`. The fix was to include `s.created_at` in the ClawHub-specific Python reader and
map it to `createdAt` before producing epoch milliseconds.

## Risks And Follow-Up

- Vite method-aware routing is now active for this one canonical GET route. Future routes with
  method collisions must keep using method-aware tests and live gates.
- `GET /api/v1/skills` is still Java-owned and should not be migrated without a separate plan
  because it shares the root path with Java-owned `POST /api/v1/skills`.
- Download, publish, delete, undelete, auth/session, and mutation routes remain deferred.
