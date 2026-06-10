# Admin Password Reset Trigger Migration Result

## Summary

Moved the admin-triggered password reset route to FastAPI:

- `POST /api/v1/admin/users/{userId}/password-reset`

Anonymous local password reset request/confirm, OAuth, sessions, and API-token routes remain
Java-owned.

## Changes

- Added Python admin reset service logic in `server-python/app/admin/users.py`.
- Added FastAPI route in `server-python/app/api/admin_users.py`.
- Added `bcrypt` to `server-python` so reset code hashes remain Java BCrypt-compatible.
- Moved Vite dev proxy ownership for the admin reset trigger route to Python.
- Added Windows live gate target:
  `verify-admin-password-reset-smoke`.
- Updated route ownership documentation and migration sequence.

## Behavior Preserved

- Requires `USER_ADMIN` or `SUPER_ADMIN`.
- Missing user returns Java-compatible not-found behavior.
- Ineligible targets return Java-compatible bad-request behavior:
  inactive/disabled user, blank email, or missing local credential.
- Success consumes old pending reset requests.
- Success inserts a new `password_reset_request` with:
  - BCrypt-looking `code_hash`;
  - `requested_by_admin = true`;
  - `requested_by_user_id = local-admin` in the live fixture;
  - future expiry.
- Response envelope keeps `code = 0` and `data = null`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_admin_user_management.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-password-reset-smoke
```

Results:

- Python narrow tests: `12 passed`.
- Vite proxy tests: `34 passed`.
- Windows live gate:
  - Python/proxy success envelopes matched.
  - Python/proxy DB reset rows were persisted with consumed old requests and BCrypt hashes.
  - Missing user status parity: Java/Python/proxy `404`.
  - Disabled user status parity: Java/Python/proxy `400`.
  - No-email status parity: Java/Python/proxy `400`.
  - No-credential status parity: Java/Python/proxy `400`.
  - Non-admin status parity: Java/Python/proxy `403`.
  - Playwright smoke: `6 passed`.

## Notes And Risks

- Java success path sends email. The local hybrid gate has no SMTP mock, so it verifies Java
  parity on non-email error paths and verifies Python/proxy success through response and DB
  contract checks.
- Python exposes a sender hook, but no production SMTP adapter has been migrated yet. Before
  replacing local-auth reset flows in production, add the email adapter and a success-path parity
  gate with a test SMTP sink.
- The plan file still references the Java i18n key as the durable response contract; the rendered
  Chinese message can be checked through live response output when encoding matters.
