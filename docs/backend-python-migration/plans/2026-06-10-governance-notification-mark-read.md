# Governance Notification Mark-Read Migration Plan

## Summary

Move the legacy governance notification mark-read mutation from Java to FastAPI.
This completes the write side left behind by the governance workbench read
milestone while keeping the broader notification SSE and auth/token surfaces out
of scope.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/governance/notifications/{id}/read`
- `POST /api/web/governance/notifications/{id}/read`

Unchanged:

- Governance workbench read APIs remain Python-owned.
- `/api/v1/notifications/sse` and `/api/web/notifications/sse` remain Java-owned.
- Auth, OAuth, API tokens, and notification preference routes are not changed by
  this milestone.

## Java Contract Reference

Reference files, read-only:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/GovernanceController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/governance/GovernanceNotificationService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/governance/UserNotification.java`
- `server/skillhub-app/src/test/java/com/iflytek/skillhub/controller/GovernanceControllerTest.java`

Observed Java behavior:

- Requires current authenticated user.
- Finds `user_notification` by id.
- Missing id returns `error.notification.notFound`.
- Notification owned by another user returns `error.notification.noPermission`.
- Success sets `status = READ`, sets `read_at = now`, saves, and returns the
  updated notification DTO.
- Success envelope uses `response.success.updated` (`更新成功`).

## Implementation Scope

Allowed edits:

- `server-python/app/api/governance.py`
- `server-python/app/governance/workbench.py`
- `server-python/tests/test_governance_workbench.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Database schema changes.
- Auth/session/OAuth/API token behavior.
- Notification SSE ownership.

## Test Plan

- Add unit tests for:
  - mark-read updates only the target `user_notification` row;
  - returned DTO matches Java field names and timestamp formatting;
  - missing id maps to `error.notification.notFound`;
  - foreign user maps to `error.notification.noPermission`;
  - route envelope uses `更新成功`;
  - anonymous requests remain `401`.
- Update Vite proxy tests so both POST routes go to Python.
- Update hybrid Windows gate with Java/Python/proxy comparison for:
  - success mark-read envelope and persisted status/read_at;
  - missing id status parity;
  - foreign-user status parity;
  - governance read route remains Python and SSE remains Java.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_governance_workbench.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-governance-notification-mark-read-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python tests.
- [x] Implement FastAPI mark-read behavior.
- [x] Move Vite proxy ownership for the two POST routes.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.
