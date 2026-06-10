# Local Password Reset Migration Plan

## Summary

Move anonymous local-account password reset request/confirm routes to FastAPI. This follows the
admin password reset milestone and reuses the same `password_reset_request` storage contract.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/auth/local/password-reset/request`
- `POST /api/v1/auth/local/password-reset/confirm`

Unchanged:

- `POST /api/v1/auth/local/register` remains Java-owned.
- `POST /api/v1/auth/local/login` remains Java-owned.
- `POST /api/v1/auth/local/change-password` remains Java-owned.
- `/oauth2/**`, session bootstrap, device flow, and bearer-token authentication remain Java-owned.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/LocalAuthController.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/PasswordResetService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/PasswordPolicyValidator.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/PasswordResetRequestDto.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/PasswordResetConfirmRequest.java`
- `server/skillhub-app/src/main/resources/db/migration/V39__password_reset_request.sql`

Expected behavior:

- Request:
  - trims/lowercases email;
  - rejects blank or invalid email;
  - silently succeeds for unknown, disabled, blank-email, or no-local-credential users;
  - consumes pending reset requests for eligible users;
  - inserts a new non-admin reset request with BCrypt code hash;
  - does not throw if email sending fails in anonymous flow.
- Confirm:
  - validates email and six-digit code shape;
  - returns `error.auth.password.reset.invalid.code` for missing user or unmatched/expired code;
  - validates new password with Java policy: length 8..128 and at least 3 character classes;
  - returns `error.auth.password.reset.no.credential` if the user has no local credential;
  - updates `local_credential.password_hash`, resets failed attempts and locked state;
  - consumes the matched request and any remaining pending reset requests for that user.

## Implementation Scope

Allowed edits:

- `server-python/app/auth/password_reset.py`
- `server-python/app/api/local_auth.py`
- `server-python/app/main.py`
- `server-python/tests/test_local_password_reset.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Local register/login/change-password.
- OAuth/session/device-flow routes.
- Bearer token authentication and scope enforcement.
- Database schema changes.

## Test Plan

- Unit tests:
  - request inserts only for eligible users and silently succeeds for unknown/ineligible users;
  - request consumes old pending rows and stores BCrypt hashes;
  - confirm validates code, password policy, and local credential presence;
  - confirm updates credential and consumes all pending reset requests.
- Route tests:
  - request/confirm return Java-compatible envelopes;
  - invalid email/code/password return HTTP `400`.
- Vite tests:
  - password reset request/confirm route to Python;
  - other `/api/v1/auth/local/**` routes remain Java-owned.
- Windows live gate:
  - Java/Python/proxy compare request success and invalid email;
  - Java/Python/proxy compare confirm success from seeded BCrypt reset rows;
  - Java/Python/proxy compare invalid code and weak password statuses;
  - DB checks prove request rows are created/consumed correctly and credentials are updated.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_local_password_reset.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-local-password-reset-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Implement password reset service and FastAPI routes.
- [x] Move Vite proxy ownership for reset request/confirm only.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [ ] Commit and push to `origin/dev`.
