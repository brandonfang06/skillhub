# Local Auth Core Migration Result

## Summary

Moved local password account core routes to FastAPI:

- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`

Password reset was already Python-owned. OAuth callbacks, direct login, session bootstrap, device
flow, bearer-token authentication filters, scope enforcement, and notification SSE remain
Java-owned.

## Route Ownership

Before:

- `POST /api/v1/auth/local/register` -> Java
- `POST /api/v1/auth/local/login` -> Java
- `POST /api/v1/auth/local/change-password` -> Java

After:

- `POST /api/v1/auth/local/register` -> Python
- `POST /api/v1/auth/local/login` -> Python
- `POST /api/v1/auth/local/change-password` -> Python

## Java Parity

Preserved behavior:

- Register trims/lowercases username and email.
- Register enforces Java username regex, email format, duplicate username/email checks, and
  password policy.
- Register creates `user_account`, `local_credential`, and global namespace membership.
- Login uses BCrypt-compatible verification, rejects disabled/pending/merged users, increments
  failed attempts, locks after the fifth failure, and resets lock state on success.
- Change-password requires current user auth through the hybrid mock-user bridge, verifies current
  password, enforces the same password policy, updates the hash, and resets failed attempts/lock.
- Responses preserve Java `AuthMeResponse` fields with `oauthProvider = "local"` and default
  `USER` role fallback.

Explicitly deferred:

- Java establishes a Spring web session after register/login. Python now owns the API/database
  behavior but does not create Spring Session rows. Hybrid local follow-up auth still uses the
  existing `X-Mock-User-Id` bridge until final auth/session replacement.

Live gate caught and fixed:

- Register fixture usernames initially used `-`, but Java only allows letters, digits, and `_`.
  The gate data now uses valid underscore usernames.
- Change-password comparison initially included localized `msg`; Java returns localized text while
  Python stores message keys. The gate now compares stable `code/data` fields for this void
  mutation.
- A parity self-check caught that Java verifies the current password before validating the new
  password policy. Python was adjusted to return `error.auth.local.invalidCredentials` for
  wrong-current-password requests even when the new password is weak, and the live gate now checks
  that Java/Python/proxy all return `401` for that case.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_local_auth_core.py tests/test_local_password_reset.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-local-auth-core-smoke
```

Results:

- Python local-auth/password-reset/hybrid-script tests: `19 passed, 1 warning`.
- Vite proxy tests: `38 passed`.
- Windows live gate: passed.
- Playwright smoke inside live gate: `6 passed`.
- Live gate included `wrongCurrentBeforeWeakNewParity = true`.

Live gate artifact:

- `.dev/local-auth-core-contract-result.json`

## Risks And Follow-Up

- Session creation remains deferred. Final auth/session replacement must decide whether Python owns
  session cookies, Redis/Spring Session compatibility, or a new session model.
- Direct login, session bootstrap, OAuth callbacks, device flow, bearer-token filters, scope
  enforcement, and notification SSE are still Java-owned and must stay carved out during proxy
  cleanup.
