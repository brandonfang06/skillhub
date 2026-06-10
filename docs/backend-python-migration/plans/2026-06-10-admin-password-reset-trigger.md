# Admin Password Reset Trigger Migration Plan

## Summary

Move the admin-triggered local-account password reset endpoint to FastAPI.
This is the last endpoint in the admin user-management group that remained
Java-owned.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/admin/users/{userId}/password-reset`

Unchanged:

- `POST /api/v1/auth/local/password-reset/request` remains Java-owned.
- `POST /api/v1/auth/local/password-reset/confirm` remains Java-owned.
- OAuth, session, and API-token routes remain Java-owned.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/UserManagementController.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/PasswordResetService.java`
- `server/skillhub-app/src/main/resources/db/migration/V39__password_reset_request.sql`
- `server/skillhub-app/src/test/java/com/iflytek/skillhub/controller/admin/UserManagementControllerTest.java`

Expected behavior:

- Requires `USER_ADMIN` or `SUPER_ADMIN`.
- Missing principal/auth returns `error.auth.required`.
- Missing target user returns `error.admin.user.notFound`.
- Ineligible target returns `error.auth.password.reset.not.eligible`:
  - user status is not `ACTIVE`;
  - email is blank;
  - local credential row is missing.
- Success:
  - consumes existing pending password reset requests for the user;
  - creates a new `password_reset_request`;
  - stores a BCrypt-compatible `code_hash`;
  - sets `requested_by_admin = true`;
  - sets `requested_by_user_id` to the admin actor;
  - uses Java default expiry of 10 minutes unless configured later;
  - returns `response.auth.password.reset.requested`
    (`如果账号符合条件，密码重置验证码已发送。`) with `data = null`.

## Implementation Scope

Allowed edits:

- `server-python/app/admin/users.py`
- `server-python/app/api/admin_users.py`
- `server-python/tests/test_admin_user_management.py`
- `server-python/tests/test_hybrid_makefile.py`
- `server-python/pyproject.toml`
- `server-python/uv.lock`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Anonymous password reset request/confirm routes.
- OAuth/session/API-token behavior.
- Database schema changes.

## Dependency Change

Add Python `bcrypt` so generated reset request rows remain compatible with Java
BCrypt verification semantics. Do not replace BCrypt with a plain hash.

## Test Plan

- Unit tests:
  - admin trigger consumes old pending reset requests;
  - inserts a new request with BCrypt-looking hash and admin metadata;
  - rejects missing user and inactive/no-email/no-credential target;
  - route enforces admin roles and returns Java success envelope.
- Vite tests:
  - route now resolves to Python instead of Java fallback.
- Windows live gate:
  - compare Python/proxy success envelopes because Java success sends email and local hybrid has no SMTP mock;
  - verify DB state for each Python/proxy success path has one fresh admin reset request;
  - verify old pending request is consumed;
  - verify missing/disabled/no-email/no-credential/forbidden Java/Python/proxy status parity.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_admin_user_management.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-password-reset-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Implement admin password reset trigger in FastAPI.
- [x] Move Vite proxy ownership for the route.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.
