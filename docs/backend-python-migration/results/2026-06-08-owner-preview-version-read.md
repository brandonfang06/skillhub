# Owner Preview Version Read Result

Date: 2026-06-08

## Summary

Extended Python-owned skill version read routes with Java-compatible lifecycle-manager access:

- `GET /api/v1/skills/{namespace}/{slug}/versions`
- `GET /api/web/skills/{namespace}/{slug}/versions`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`

Anonymous and non-manager callers still see only published versions. Skill owners and namespace
`OWNER` / `ADMIN` callers can now list and read non-published lifecycle versions allowed by Java.

## Behavior Implemented

- Version list for anonymous/non-manager callers:
  - only `PUBLISHED`.
- Version list for lifecycle managers:
  - `PUBLISHED`
  - `REJECTED`
  - `PENDING_REVIEW`
  - `UPLOADED`
  - `DRAFT`
  - `SCANNING`
  - `SCAN_FAILED`
  - `YANKED`
- Manager list ordering follows Java:
  - lifecycle status priority;
  - `published_at` descending with nulls last;
  - `created_at` descending with nulls last;
  - `id` descending.
- Version detail:
  - published detail remains visible to public callers;
  - non-published detail is visible only to lifecycle managers;
  - non-manager non-published detail returns `400`, matching Java live behavior.

## Deferred

- Owner-preview file metadata remains deferred.
- File bytes, bundle downloads, storage reads, download counters, and download redirects remain
  Java-owned.
- Non-public visibility for private, hidden, inactive, or archived skills remains deferred.
- Publish, review, promotion, lifecycle, OAuth, token, and session mutations remain Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_versions.py`
- `server-python/tests/test_skill_versions_repository.py`
- `server-python/tests/test_skill_version_detail.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-owner-preview-version-read.md`
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-version-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `anonymousListPublishedOnly: true`
- `ownerListIncludesPreviewStates: true`
- `anonymousPendingDetailStatusesMatch: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- anonymous version list
- owner version list via `X-Mock-User-Id: local-user`
- namespace admin version list via `X-Mock-User-Id: local-admin`
- owner pending version detail
- namespace admin pending version detail
- anonymous pending version detail HTTP status through Java, Python, Vite `/api/v1`, and Vite
  `/api/web`

Artifact:

- `.dev/owner-preview-version-contract-result.json`

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

- `117 passed, 1 warning`

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
- Owner-preview file metadata is not yet migrated, so frontend flows that drill from preview
  version detail into files still require a future milestone.
- Non-public visibility remains intentionally narrower than Java manager behavior until explicitly
  planned.

## Follow-Up

- Next low-risk continuation: owner-preview file metadata for version files.
- Do not start publish/upload until auth and storage assumptions are explicitly planned.
