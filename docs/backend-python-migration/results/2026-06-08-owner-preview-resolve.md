# Owner Preview Resolve Result

Date: 2026-06-08

## Summary

Added authenticated context forwarding and live Java parity coverage for portal skill resolve
routes:

- `GET /api/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/web/skills/{namespace}/{slug}/resolve`

Important finding: Java portal resolve remains published-only even for skill owners and namespace
admins. Python now forwards the local mock user context through the route boundary, but keeps
non-published owner-preview resolve rejected to match Java.

## Behavior Implemented

- Portal resolve now normalizes and forwards `X-Mock-User-Id`.
- Published exact version resolve remains unchanged for:
  - anonymous callers;
  - skill owner;
  - namespace `ADMIN`.
- Exact `PENDING_REVIEW` resolve remains rejected for:
  - anonymous callers;
  - skill owner;
  - namespace `ADMIN`.
- ClawHub `/api/v1/resolve` routes keep their previous reader signature and behavior.

## Deferred

- Non-published owner-preview resolve targets are not enabled because Java does not allow them.
- Tag owner-preview resolve remains published-only through Java-compatible behavior.
- File bytes, bundle downloads, storage streaming, redirect headers, download counters, and
  download metrics remain Java-owned.
- Non-public visibility for private, hidden, inactive, or archived skills remains deferred.
- Publish, review, promotion, lifecycle, OAuth, token, and session mutations remain Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_resolve.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-owner-preview-resolve.md`
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-resolve-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `publishedVersionResolved: true`
- `publishedDownloadUrlKept: true`
- `anonymousPendingStatusesMatch: true`
- `ownerPendingStatusesMatch: true`
- `namespaceAdminPendingStatusesMatch: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- anonymous published exact version resolve
- owner published exact version resolve via `X-Mock-User-Id: local-user`
- namespace admin published exact version resolve via `X-Mock-User-Id: local-admin`
- anonymous pending exact version resolve HTTP status through Java, Python, Vite `/api/v1`, and
  Vite `/api/web`
- owner pending exact version resolve HTTP status through Java, Python, Vite `/api/v1`, and Vite
  `/api/web`
- namespace admin pending exact version resolve HTTP status through Java, Python, Vite `/api/v1`,
  and Vite `/api/web`

Artifact:

- `.dev/owner-preview-resolve-contract-result.json`

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

- `119 passed, 1 warning`

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

- The route forwards `current_user_id`, but the repository still intentionally uses the existing
  public/published SQL boundary. This matches current Java portal resolve behavior, but it means
  future non-public resolve support requires a separate design.
- Download URLs are only metadata here. Download route behavior is still Java-owned.

## Follow-Up

- Next low-risk continuation: version compare owner-preview access, because Java already has
  `assertPreviewAccessible(...)` for compare.
- Before moving downloads or file bytes, write the Group B storage bridge design.
