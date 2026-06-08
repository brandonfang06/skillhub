# Skill Detail Owner Preview Result

Date: 2026-06-08

## Summary

Extended the Python-owned public skill detail routes with Java-compatible manager-only owner
preview projection:

- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`

Anonymous public detail remains unchanged. Owners and namespace `OWNER` / `ADMIN` viewers can now
see a newer non-published, non-yanked owner preview version in the detail projection when Java would
surface it.

## Behavior Implemented

- `ownerPreviewVersion` is populated only for lifecycle managers:
  - skill owner; or
  - namespace `OWNER` / `ADMIN`.
- Preview candidate follows Java `SkillLifecycleProjectionService`:
  - exclude `PUBLISHED` and `YANKED`;
  - require preview recency newer than the resolved published version;
  - choose newest by `created_at`, then `id`.
- Published public skills keep:
  - `headlineVersion = publishedVersion`;
  - `resolutionMode = PUBLISHED`;
  - `canInteract = true`.
- Preview-only manager-visible details use:
  - `headlineVersion = ownerPreviewVersion`;
  - `resolutionMode = OWNER_PREVIEW`;
  - `canInteract = false`.
- Rejected owner preview versions expose `ownerPreviewReviewComment` from the rejected review task.

## Deferred

- Non-public detail visibility for private, hidden, or archived skills remains deferred.
- Owner-preview access for version detail, version list, file metadata, resolve, file content, and
  download routes remains deferred.
- Publish, review, promotion, lifecycle, storage, OAuth, token, and session mutations remain
  Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_detail_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-skill-detail-owner-preview.md`
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-detail-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `anonymousHidesPreview: true`
- `ownerSeesRejectedPreview: true`
- `ownerSeesReviewComment: true`
- `namespaceAdminSeesRejectedPreview: true`
- `publishedHeadlineKept: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- anonymous public detail request
- owner request via `X-Mock-User-Id: local-user`
- namespace admin request via `X-Mock-User-Id: local-admin`

Artifact:

- `.dev/owner-preview-detail-contract-result.json`

Cleanup check:

- Docker containers: none running.
- Ports `3000`, `8080`, and `8081`: no `LISTENING` entries; `TIME_WAIT` entries remained.

## Debug Notes

The first live gate attempt failed before contract comparison because the SQL fixture used a
PL/pgSQL variable named `skill_id`, which conflicted with `ON CONFLICT (skill_id, version)`. The
fixture variable was renamed.

The second live gate attempt found a Python 500 in the owner case. Root cause: asyncpg could not
infer a bind parameter type when the preview SQL used the same parameter in `IS NULL` checks and
numeric comparisons. The query was split by published-version state so each parameter is typed by a
concrete comparison.

## Unit And Static Verification

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result:

- `112 passed, 1 warning`

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

- This still relies on the local mock-user bridge, not a production session or SSO bridge.
- Owner preview currently applies only to public detail routes; frontend flows that need preview
  version files or download must wait for a separate route group.
- SQL recency logic intentionally mirrors Java null ordering; future schema changes around
  `created_at` should be covered by live comparison.

## Follow-Up

- Decide whether the next Group C milestone should cover owner-preview version/file routes,
  viewer-specific list/search, namespace role helpers, or session-cookie compatibility.
- Do not start publish/upload until auth and storage assumptions are explicitly planned.
