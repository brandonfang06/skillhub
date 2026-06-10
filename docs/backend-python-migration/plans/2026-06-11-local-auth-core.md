# Local Auth Core Migration Plan

## Summary

Move the remaining local password account core routes to FastAPI:

- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`

This extends the already-migrated local password reset routes. OAuth callbacks, device flow,
direct-login, session bootstrap, bearer-token authentication filters, and notification SSE remain
Java-owned.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`

Unchanged ownership:

- `POST /api/v1/auth/local/password-reset/request` and
  `POST /api/v1/auth/local/password-reset/confirm` are already Python-owned.
- `POST /api/v1/auth/session/bootstrap` remains Java-owned.
- `POST /api/v1/auth/direct/login` remains Java-owned.
- `/oauth2/**` remains Java-owned.
- Bearer-token authentication filters and scope enforcement remain Java-owned.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/LocalAuthController.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/LocalAuthService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/PasswordPolicyValidator.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/LocalRegisterRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/LocalLoginRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/ChangePasswordRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AuthMeResponse.java`
- Flyway schemas: `V1__init_schema.sql`, `V5__phase4_auth_governance.sql`,
  `V21__user_account_timestamptz.sql`, and `V22__auth_supporting_tables_timestamptz.sql`.

Expected behavior:

- Register:
  - trims and lowercases username;
  - validates username with `^[A-Za-z0-9_]{3,64}$`;
  - rejects duplicate username case-insensitively with `error.auth.local.username.exists`;
  - trims and lowercases email;
  - rejects missing/invalid email with Java-compatible validation keys;
  - rejects duplicate email case-insensitively with `error.auth.local.email.exists`;
  - enforces Java password policy: length 8..128 and at least 3 character categories;
  - creates `usr_<uuid>` active user, `local_credential`, and global namespace membership;
  - returns `AuthMeResponse` with `oauthProvider = "local"` and default `USER` role when no
    platform binding exists.
- Login:
  - trims and lowercases username;
  - rejects missing/unknown/bad password with `error.auth.local.invalidCredentials`;
  - rejects `DISABLED`, `PENDING`, and `MERGED` accounts with Java-compatible keys;
  - locks the credential for 15 minutes after 5 failed attempts;
  - resets failed attempts and lock on success;
  - returns `AuthMeResponse` with `oauthProvider = "local"`.
- Change password:
  - requires current user auth through the existing hybrid mock-user bridge;
  - rejects users without local credentials with `error.auth.local.notEnabled`;
  - verifies current password;
  - applies the same Java password policy to the new password;
  - resets failed attempts and lock state after password update.

Session note:

- Java establishes a Spring web session after register/login. The Python migration preserves the
  API response and database contract, but does not create a Spring Session row. During hybrid local
  development, authenticated follow-up calls still use the existing `X-Mock-User-Id` bridge until
  the final auth/session replacement milestone.

## Implementation Scope

Allowed edits:

- `server-python/app/auth/local.py`
- `server-python/app/api/local_auth.py`
- `server-python/tests/test_local_auth_core.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Java Flyway schema edits.
- OAuth/session bootstrap/direct-login/device-flow changes.
- Generated OpenAPI TypeScript edits.
- Frontend page/client behavior changes.

## Test Plan

- Unit/service tests:
  - register success creates user, credential, and global namespace membership;
  - register lowercases username/email and rejects duplicate username/email;
  - register rejects weak passwords with Java-compatible keys;
  - login success returns local principal and clears failure state;
  - failed login increments attempts and locks after the fifth failure;
  - disabled/pending/merged users are rejected;
  - change-password verifies current password, updates hash, and resets lock state.
- Route tests:
  - register/login return Java-compatible envelopes;
  - change-password requires `X-Mock-User-Id`;
  - change-password rejects wrong current password.
- Vite tests:
  - local register/login/change-password route to Python;
  - password reset routes remain Python-owned;
  - direct login, session bootstrap, and OAuth remain Java-owned.
- Windows live gate:
  - compare Java/Python/proxy stable response and DB state for isolated register/login/change
    fixtures;
  - verify invalid password and duplicate username/email status parity;
  - verify direct-login/session-bootstrap still route to Java.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_local_auth_core.py tests/test_local_password_reset.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-local-auth-core-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing service/route/Vite/hybrid-script tests.
- [x] Implement Python local auth core service and routes.
- [x] Move Vite proxy ownership for local register/login/change-password only.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.
