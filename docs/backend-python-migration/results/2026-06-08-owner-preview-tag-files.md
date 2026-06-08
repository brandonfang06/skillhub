# Owner Preview Tag Files Parity Result

## Summary

Completed authenticated context forwarding and live contract coverage for tag file metadata routes.
No owner-preview access was enabled for tag selectors because Java keeps tag file metadata
published-only.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | python, published-only | python, published-only with authenticated context forwarding |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python, published-only | python, published-only with authenticated context forwarding |

## Java Reference Finding

Java `SkillQueryService.listFilesByTag(...)` accepts `currentUserId` and `userNsRoles`, but resolves
the tag version through `resolveVersionEntity(skill, null, tagName, null)`. That path enforces
published-only behavior instead of calling `assertPreviewAccessible(...)`.

Resulting parity rule:

- published tag file metadata remains readable.
- pending/rejected/draft tag targets remain rejected for anonymous callers, skill owners, and
  namespace admins.

## Implementation

- `server-python/app/api/skills.py`
  - `list_skill_tag_files(...)` now accepts `X-Mock-User-Id`.
  - The route normalizes blank headers to `None`.
  - Injected test readers and the DB reader receive `current_user_id`.
  - `read_skill_tag_files(...)` accepts `current_user_id` but intentionally keeps its
    `status = 'PUBLISHED'` SQL filter.
- `server-python/tests/test_skill_file_metadata.py`
  - Added tag route reader forwarding coverage.
- `scripts/dev-hybrid.ps1`
  - Added `verify-owner-preview-tag-files-smoke`.
  - Added deterministic published and pending tag fixtures.
  - Compares Java, Python, Vite `/api/v1`, and Vite `/api/web` contracts.
- `server-python/tests/test_hybrid_makefile.py`
  - Added static coverage for the new Windows live gate.
- Docs updated:
  - `docs/backend-python-migration/route-registry.md`
  - `docs/backend-python-migration/migration-sequence-plan.md`
  - `docs/backend-python-migration/windows-live-verification.md`

## Verification

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result: `126 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
```

Result: `16 passed`.

Passed:

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
```

Passed with no output.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-tag-files-smoke
```

Live gate result:

- published anonymous/owner/admin tag file metadata matched Java/Python/Vite.
- pending anonymous/owner/admin tag file metadata all returned `400`.
- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `publishedFilesSorted: true`
- `allPendingStatusesMatch: true`
- `allPendingRejected: true`
- Playwright smoke: `6 passed`.

Artifact:

```text
.dev/owner-preview-tag-files-contract-result.json
```

Cleanup check:

- no `LISTENING` process remained on ports `3000`, `8080`, or `8081`.
- no Docker containers remained running for the local stack.

## Risks

- Tag file metadata keeps Java's current `400` rejection for non-published tag targets. This is
  intentional parity, not a redesigned API shape.
- The DB reader receives `current_user_id` only for route parity and future-proofing; it must not
  use that value to broaden tag access unless Java behavior changes or a deliberate product
  redesign is approved.

## Follow-Up

- Continue converting protected read APIs only after adding equivalent Java/Python/Vite live
  contract gates.
- File bytes and downloads remain Java-owned.
- Mutating, OAuth, session, API token, idempotency, and lifecycle routes remain deferred.
