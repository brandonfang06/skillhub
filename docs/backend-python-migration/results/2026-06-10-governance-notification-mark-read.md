# Governance Notification Mark-Read Migration Result

## Summary

Moved the legacy governance notification mark-read mutation to FastAPI.

Python-owned routes:

- `POST /api/v1/governance/notifications/{id}/read`
- `POST /api/web/governance/notifications/{id}/read`

Unchanged:

- Governance workbench read APIs remain Python-owned.
- Notification SSE remains Java-owned.
- Auth/OAuth/API-token and admin password reset surfaces were not changed.

## Behavior Preserved

- Requires authenticated mock user.
- Reads and updates the legacy `user_notification` table.
- Missing id returns `error.notification.notFound`.
- Foreign-user notification returns `error.notification.noPermission`.
- Success sets `status = READ`, sets `read_at`, and returns the updated notification DTO.
- Success envelope uses Java-compatible `更新成功`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_governance_workbench.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-governance-notification-mark-read-smoke
```

Results:

- Python tests: `13 passed`.
- Vite proxy tests: `34 passed`.
- Windows live gate: passed.
- Playwright smoke in live gate: `6 passed`.
- Live Java/Python/proxy checks:
  - success envelope parity: true;
  - Java/Python/proxy DB state all `READ|set`;
  - missing-id status parity: `404`;
  - foreign-user status parity: `403`.

## Issues Found And Fixed

- Initial live gate showed Python and proxy responses returned `READ`, but DB state remained
  `UNREAD|null` after the request. Root cause: the mutation used a plain connection instead of a
  transaction boundary. Fixed by using `engine.begin()` for mark-read.
- Stable comparison initially differed because fixture titles included `Java`, `Python`, and
  `Proxy` suffixes. Fixed the live gate stable serializer to normalize those fixture-only suffixes.

## Files Changed

- `server-python/app/governance/workbench.py`
- `server-python/app/api/governance.py`
- `server-python/tests/test_governance_workbench.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-10-governance-notification-mark-read.md`

## Remaining Work

- Notification SSE remains Java-owned.
- Admin password reset remains Java-owned.
- Auth/OAuth/API-token surfaces remain Java-owned.
- Final proxy cleanup and Python module refactor remain future milestones.
