# Owner Preview Version Compare Result

Date: 2026-06-08

## Summary

Migrated portal skill version compare routes to Python:

- `GET /api/v1/skills/{namespace}/{slug}/versions/compare`
- `GET /api/web/skills/{namespace}/{slug}/versions/compare`

Skill owners and namespace `OWNER` / `ADMIN` callers can compare Java-allowed non-published owner
preview versions. Anonymous callers remain restricted to published versions.

## Behavior Implemented

- Added Python compare route ownership for both v1 and web aliases.
- Added Java-shaped compare response:
  - `from`
  - `to`
  - `summary`
  - `files`
  - `hunks`
  - ADD/DELETE lines
- Added local storage text reads through `SKILLHUB_STORAGE_BASE_PATH`.
- Added Java-compatible trailing newline behavior for text diff lines.
- Same-version compare returns `400`, matching Java.
- Anonymous compare involving `PENDING_REVIEW` returns `400`, matching Java.

## Deferred

- File bytes and download endpoints remain Java-owned.
- MinIO/S3 streaming behavior remains deferred to Group B storage/download design.
- Non-public visibility for private, hidden, inactive, or archived skills remains deferred.
- Publish, review, promotion, lifecycle, OAuth, token, and session mutations remain Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/app/core/config.py`
- `server-python/tests/test_skill_version_compare.py`
- `server-python/tests/test_config.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-owner-preview-version-compare.md`
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-compare-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- `previewSummaryMatchesFixture: true`
- `previewFilesSorted: true`
- `anonymousPreviewStatusesMatch: true`
- `sameVersionStatusesMatch: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- owner published-to-pending version compare via `X-Mock-User-Id: local-user`
- namespace admin published-to-pending version compare via `X-Mock-User-Id: local-admin`
- anonymous published-to-pending version compare HTTP status through Java, Python, Vite `/api/v1`,
  and Vite `/api/web`
- owner same-version compare HTTP status through Java, Python, Vite `/api/v1`, and Vite `/api/web`

Artifact:

- `.dev/owner-preview-compare-contract-result.json`

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

- `125 passed, 1 warning`

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

## Debugging Note

The first live gate run found a Java/Python contract mismatch. Root cause:

- Java uses `content.split("\\R", -1)` for compare lines, so files ending in a newline include a
  trailing empty string line.
- Python initially used `splitlines()`, which drops that trailing empty line.
- The compare route also initially used a bad mojibake success message literal.

Fix:

- Python now preserves a trailing empty line when text content ends with `\n` or `\r`.
- The compare route now uses the same `获取成功` success message as existing Python-owned portal
  routes.

## Risks

- Python compare currently reads local filesystem storage. S3/MinIO object storage parity is still
  part of the future Group B storage bridge.
- Binary and truncated response shape is implemented, but the live gate focuses on small text-file
  diffs.

## Follow-Up

- Next low-risk continuation: tag owner-preview parity or another protected read API.
- Before moving downloads or file bytes, write the Group B storage bridge design.
