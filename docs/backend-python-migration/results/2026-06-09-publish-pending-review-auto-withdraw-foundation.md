# Publish Pending Review Auto-Withdraw Foundation Result

## Summary

Completed Python publish pending-review auto-withdraw foundation for direct CLI publish.

No route ownership changed.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Direct Python backend on port `8081` now withdraws earlier pending-review versions for the same
  skill before inserting the next publish version.

## Routes Changed

None.

## Owner Before / After

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` through Vite | Java | Java |
| Direct Python `POST /api/cli/v1/skills/{namespace}/publish` | Python foundation only | Python foundation only |

## Behavior Implemented

- Added `auto_withdraw_pending_review_versions(...)`.
- The helper selects existing `PENDING_REVIEW` versions for the skill.
- Pending `review_task` rows for those versions are deleted.
- Those versions are moved back to `UPLOADED`.
- Existing published versions are untouched.
- The orchestration runs auto-withdraw before replacement cleanup and before inserting the new
  `skill_version`.

## Java Parity Checklist Outcome

- Java reference: `SkillPublishService`.
- API contract: covered for direct Python publish foundation; Vite route ownership remains Java.
- Authorization/session behavior: unchanged; Python direct route still uses local mock-user bridge.
- Database transaction atomicity: covered inside the existing publish write transaction.
- Audit actor/timestamp fields: not applicable for this helper because the current schema has no
  `skill_version.updated_by` or `skill_version.updated_at` columns.
- Storage and side effects: unchanged.
- Live verification evidence: covered by Windows live gate.

## Verification

Narrow tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='server-python\.uv-cache'
uv run pytest tests/test_publish_auto_withdraw.py tests/test_publish_orchestration.py tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q
```

Result:

- `20 passed, 1 warning`

Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-pending-auto-withdraw-smoke
```

Result:

- Python direct first publish: `200`
- Python direct second publish: `200`
- First version before second publish: `PENDING_REVIEW`
- First version after second publish: `UPLOADED`
- Pending review task count before: `1`
- Pending review task count after: `0`
- Second version status: `PENDING_REVIEW`
- Vite proxy ownership check: Java status `401`, proxy status `401`
- Playwright smoke: `6 passed`

The gate emitted taskkill warnings during teardown, but a follow-up port check found no listeners
on `3000`, `8080`, `8081`, or `8000`.

## Risks

- This milestone does not move publish write ownership through Vite.
- Scanner result processing remains a later publish migration concern.
- Storage failure cleanup evidence remains a required publish parity gap before route ownership
  moves.

## Follow-Up

- Add storage-failure cleanup proof for Python publish write.
- Expand repeated publish Java/Python live matrix before moving
  `POST /api/cli/v1/skills/{namespace}/publish` ownership.
