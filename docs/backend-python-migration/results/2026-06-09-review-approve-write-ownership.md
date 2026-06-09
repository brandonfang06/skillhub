# Review Approve Write Ownership Result

## Summary

Moved review approval write ownership to Python:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`

The route publishes the reviewed skill version, updates the parent skill latest version,
visibility, display metadata, and `updated_by`, records `REVIEW_APPROVE` audit, and returns the
Java-localized success envelope message `更新成功`.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`

Still Java-owned:

- review submit
- review reject
- review withdraw
- review list/detail
- review file/download
- promotion review APIs
- post-publish lifecycle/governance mutations

## Files Changed

- `server-python/app/api/reviews.py`
- `server-python/app/review/approval.py`
- `server-python/app/review/__init__.py`
- `server-python/app/main.py`
- `server-python/tests/test_review_approve.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-09-review-approve-write-ownership.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

No files under `server/` were modified.

## Verification

Narrow tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_review_approve.py tests/test_hybrid_makefile.py -q
```

Result: `9 passed, 1 warning`.

```powershell
cd web
$env:COREPACK_HOME=(Join-Path (Get-Location) '..\.dev\corepack')
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `20 passed`.

Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-approve-smoke
```

Result:

- Java/Python response comparison: `javaMatchesPython: true`
- Vite v1 proxy comparison: `pythonMatchesProxy: true`
- Vite web proxy comparison: `pythonMatchesProxyWeb: true`
- Java DB state check: `javaDbApproved: true`
- Python DB state check: `pythonDbApproved: true`
- Vite v1 DB state check: `proxyDbApproved: true`
- Vite web DB state check: `proxyWebDbApproved: true`
- Audit check: `auditRecorded: true`
- Playwright smoke: `6 passed`

Post-gate cleanup:

- No `3000`, `8080`, or `8081` listener remained.
- `docker ps` showed no running SkillHub containers.

Boundary check:

```powershell
git diff --name-only -- server
```

Result: empty.

## Findings

- Initial live gate failed because Python returned the raw message code
  `response.success.updated` while Java returned the localized success message `更新成功`.
  Python was updated to match Java for this mutation route.
- Initial live gate DB expectation used PostgreSQL boolean text `t`, but the PowerShell scalar
  path returned `true`. The gate now matches the actual Windows verification output.
- `UPDATE review_task` now uses `RETURNING 1` because the Python service reads the update result
  through `scalar_one()` against PostgreSQL.

## Risks / Follow-Up

- Full notification/event delivery parity for approval remains deferred. This milestone records
  audit and core DB state parity.
- Reject and withdraw are the likely next review lifecycle candidates, but their Java parity must
  be checked before grouping them.
