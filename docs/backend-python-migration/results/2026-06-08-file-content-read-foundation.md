# File Content Read Foundation Result

## Summary

Migrated portal single-file content read routes to Python as the first storage-read foundation.
Download routes remain Java-owned.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/file` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/file` | java | python |

## Java Parity Rules

- Version file content uses manager-only owner-preview access:
  - published versions are public.
  - non-published versions are readable by skill owner or namespace `OWNER` / `ADMIN`.
  - non-manager callers are rejected.
- Tag file content remains published-only:
  - published tag targets are readable.
  - non-published tag targets are rejected for anonymous, owner, and namespace admin callers.
- Response content type is `application/octet-stream`.
- Missing file rows and missing storage objects map to `error.skill.file.notFound`.

## Implementation

- Added FastAPI file content routes in `server-python/app/api/skills.py`.
- Added local storage byte reads with path traversal protection.
- Added version and tag file-content DB readers.
- Added Vite proxy ownership for the two `/api/v1/.../file` routes while keeping `/download` and
  non-existent `/api/web/.../file` aliases Java-owned.
- Added `verify-file-content-smoke` Windows live gate.

## Verification

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result: `139 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
.\node_modules\.bin\tsc.CMD --noEmit
```

Result: Vite proxy tests `16 passed`; TypeScript typecheck passed with no output.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-file-content-smoke
```

Live gate checks:

- anonymous published version text bytes.
- anonymous published version binary bytes.
- owner pending version bytes.
- namespace admin pending version bytes.
- anonymous pending version rejection.
- anonymous published tag bytes.
- owner published tag bytes.
- owner pending tag rejection.
- namespace admin pending tag rejection.
- missing file rejection.
- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allStatusesMatch: true`
- `allExpectedRejections: true`
- Playwright smoke: `6 passed`.

Artifact:

```text
.dev/file-content-contract-result.json
```

## Risks

- Python currently reads from local filesystem storage only. MinIO/S3-compatible reads remain part
  of the later storage/download design.
- Tag file content intentionally does not support owner-preview non-published tags because Java
  does not support that behavior.
- Download routes still need a separate milestone for counters, bundle objects, and headers.

## Follow-Up

- Next Group B milestone: download read path.
- Do not start publish/upload until file content and download storage behavior have passing live
  gates.
