# Review Reject/Withdraw Write Ownership Result

## Summary

Moved review reject and withdraw write ownership to Python:

- `POST /api/v1/reviews/{id}/reject`
- `POST /api/web/reviews/{id}/reject`
- `POST /api/v1/reviews/{id}/withdraw`
- `POST /api/web/reviews/{id}/withdraw`

Reject mirrors Java by moving the review task and skill version to `REJECTED`, recording reviewer
metadata and `REVIEW_REJECT` audit. Withdraw mirrors Java's submitter-only path by deleting the
pending review task, moving the version back to `UPLOADED`, updating skill `updated_by`, and
recording `REVIEW_WITHDRAW` audit.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`
- `POST /api/v1/reviews/{id}/reject`
- `POST /api/web/reviews/{id}/reject`
- `POST /api/v1/reviews/{id}/withdraw`
- `POST /api/web/reviews/{id}/withdraw`

Still Java-owned:

- review submit
- review list/detail
- review file/download
- promotion review APIs
- post-publish lifecycle/governance mutations

## Files Changed

- `server-python/app/api/reviews.py`
- `server-python/app/review/approval.py`
- `server-python/tests/test_review_reject_withdraw.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-09-review-reject-withdraw-write-ownership.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

No files under `server/` were modified.

## Verification

Narrow tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q
```

Result: `13 passed, 1 warning`.

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-reject-withdraw-smoke
```

Result:

- Reject Java/Python comparison: `javaMatchesPython: true`
- Reject Vite v1 comparison: `pythonMatchesProxy: true`
- Reject Vite web comparison: `pythonMatchesProxyWeb: true`
- Reject DB checks: `rejectDbApproved: true`
- Reject audit: `rejectAuditRecorded: true`
- Withdraw Java/Python comparison: `javaMatchesPython: true`
- Withdraw Vite v1 comparison: `pythonMatchesProxy: true`
- Withdraw Vite web comparison: `pythonMatchesProxyWeb: true`
- Withdraw DB checks: `withdrawDbApproved: true`
- Withdraw audit: `withdrawAuditRecorded: true`
- Java-owned boundary checks: `detailRemainsJavaOwned: true`, `submitRemainsJavaOwned: true`
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

- Initial live gate failed in fixture setup because the SQL seed for `skill` omitted the
  `namespace_id` value while inserting into the `namespace_id` column. The fixture now uses the
  generated `ns_id` for every seeded skill.
- Reject and withdraw both return Java-localized `更新成功` through Python, matching the previous
  approve route parity fix.

## Risks / Follow-Up

- Full async notification/event delivery parity for review reject remains deferred. This milestone
  records audit and core DB state parity.
- Review submit is the likely next write route. Review list/detail should remain separate unless
  the next plan proves their auth/query surface can be verified in one controlled gate.
