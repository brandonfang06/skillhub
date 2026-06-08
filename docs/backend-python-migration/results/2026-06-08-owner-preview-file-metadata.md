# Owner Preview File Metadata Result

Date: 2026-06-08

## Summary

Extended Python-owned version file metadata routes with Java-compatible lifecycle-manager access:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`

Anonymous and non-manager callers can still read file metadata only for published versions. Skill
owners and namespace `OWNER` / `ADMIN` callers can now read file metadata for non-published owner
preview versions.

## Behavior Implemented

- Published version file metadata remains public.
- Non-published version file metadata is visible only to lifecycle managers.
- Lifecycle manager means:
  - skill owner;
  - namespace `OWNER`;
  - namespace `ADMIN`.
- Anonymous non-published file metadata returns `400`, matching Java live behavior.
- File metadata ordering remains `filePath` ascending.

## Deferred

- Tag owner-preview file metadata remains deferred.
- File bytes, bundle downloads, storage streaming, redirect headers, download counters, and
  download metrics remain Java-owned.
- Non-public visibility for private, hidden, inactive, or archived skills remains deferred.
- Publish, review, promotion, lifecycle, OAuth, token, and session mutations remain Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_file_metadata.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-owner-preview-file-metadata.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/windows-live-verification.md`

No files under `server/` were modified.

## Live Verification

Command:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-files-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `anonymousPublishedFilesSorted: true`
- `ownerPendingFilesSorted: true`
- `anonymousPendingStatusesMatch: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- anonymous published version file metadata
- owner pending version file metadata via `X-Mock-User-Id: local-user`
- namespace admin pending version file metadata via `X-Mock-User-Id: local-admin`
- anonymous pending version file metadata HTTP status through Java, Python, Vite `/api/v1`, and
  Vite `/api/web`

Artifact:

- `.dev/owner-preview-files-contract-result.json`

Cleanup check:

- Docker containers: none running.
- Ports `3000`, `8080`, and `8081`: no `LISTENING` entries; `TIME_WAIT` entries remained.

## Unit And Static Verification

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result:

- `118 passed, 1 warning`

```powershell
cd web
node_modules\.bin\vitest.CMD vite.config.test.ts --run
```

Result:

- `16 passed`

```powershell
cd web
node_modules\.bin\tsc.CMD --noEmit
```

Result:

- exit code `0`

## Risks

- This still depends on the local `X-Mock-User-Id` bridge, not production session/SSO behavior.
- Python file metadata reads DB rows directly. Java filters through `objectStorageService.exists`.
  The live fixture includes matching local storage objects, so this milestone verifies parity for
  available file metadata. Missing-object parity remains tied to the future storage/download group.
- Tag owner-preview behavior is intentionally unchanged and remains published-only.

## Follow-Up

- Next low-risk continuation: owner-preview resolve behavior or role-helper consolidation for
  protected frontend workflows.
- Before moving downloads or file bytes, write the Group B storage bridge design.
