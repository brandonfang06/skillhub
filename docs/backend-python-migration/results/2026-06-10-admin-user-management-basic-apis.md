# Admin User Management Basic APIs Result

Date: 2026-06-10

## Scope Completed

Moved these admin user management routes to Python ownership:

- `GET /api/v1/admin/users`
- `PUT /api/v1/admin/users/{userId}/role`
- `PUT /api/v1/admin/users/{userId}/status`
- `POST /api/v1/admin/users/{userId}/approve`
- `POST /api/v1/admin/users/{userId}/disable`
- `POST /api/v1/admin/users/{userId}/enable`

Kept Java-owned:

- `POST /api/v1/admin/users/{userId}/password-reset`

## Implementation Notes

- Added `server-python/app/admin/users.py` for Java-compatible admin user listing and mutation rules.
- Added `server-python/app/api/admin_users.py` for FastAPI route ownership and response envelopes.
- Registered the router in `server-python/app/main.py`.
- Updated Vite method-aware proxy rules so only the migrated admin user routes go to Python; password reset still falls through to Java.
- Added Windows live gate coverage in `scripts/dev-hybrid.ps1`.

## Parity Checks

The Windows live gate creates isolated fixture users and compares Java, direct Python, and Vite proxy behavior for:

- list envelope, filtering, ordering, role fallback, and pagination shape
- role update response and persisted role binding
- status update response and persisted status
- enable alias behavior
- non-super-admin `SUPER_ADMIN` assignment rejection
- non-admin forbidden list access
- password reset remaining Java-owned through proxy fallback

## Debug Notes

The first live gate attempt returned a Python 500 for `GET /api/v1/admin/users`. The root cause was a stale Python backend process that had been started before the SQL fix was loaded. The SQL was also hardened by replacing nullable-parameter predicates with generated fixed WHERE clauses, avoiding asyncpg parameter type ambiguity.

After stopping the stale process and rerunning the gate from a clean local process state, the Java/Python/proxy comparison passed.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_user_management.py tests/test_hybrid_makefile.py -q`
  - Passed: 10 tests
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: 31 tests
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-user-management-smoke`
  - Passed: Python tests, Vite proxy tests, Java/Python/proxy live contract comparison, Playwright smoke
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 status`
  - Java backend stopped
  - Python backend stopped
  - Vite frontend stopped

## Risks And Follow-Up

- Password reset still depends on Java local-auth reset token behavior and remains Java-owned.
- Broader auth/token/OAuth surfaces remain Java-owned.
- Admin user APIs currently use the migration-standard raw SQL data access style. ORM/module refactor remains deferred until the planned post-migration cleanup phase.
