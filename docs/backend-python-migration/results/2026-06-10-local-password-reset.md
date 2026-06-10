# Local Password Reset Migration Result

## Summary

Moved anonymous local password reset request/confirm routes to FastAPI:

- `POST /api/v1/auth/local/password-reset/request`
- `POST /api/v1/auth/local/password-reset/confirm`

Local register, login, change-password, OAuth, session bootstrap, device flow, bearer-token auth,
and scope enforcement remain Java-owned.

## Route Ownership

| Route | Before | After |
| --- | --- | --- |
| `POST /api/v1/auth/local/password-reset/request` | java | python |
| `POST /api/v1/auth/local/password-reset/confirm` | java | python |

## Java Parity Outcome

- Request email trim/lowercase and validation are implemented at the route boundary.
- Unknown, disabled, missing-email, or no-local-credential users silently return success.
- Eligible users consume old pending reset requests and insert a new non-admin
  `password_reset_request` with BCrypt-compatible code hash.
- Sender failures are swallowed to match the anonymous Java reset flow.
- Confirm validates six-digit code shape, matched non-expired reset request, Java password policy,
  and local credential presence.
- Confirm updates `local_credential.password_hash`, resets failed attempts and lock state, and
  consumes all remaining pending reset requests for the user.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_local_password_reset.py tests/test_hybrid_makefile.py -q
```

Result: `11 passed, 1 warning`.

```powershell
cd web
npx.cmd vitest run vite.config.test.ts
```

Result: `36 passed`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-local-password-reset-smoke
```

Result: passed. The live gate compared Java, direct Python, and Vite proxy behavior for:

- request success envelope;
- request unknown-user silent success;
- request invalid-email `400`;
- confirm success envelope;
- confirm invalid-code `400`;
- confirm weak-password `400`;
- request DB contract for consumed old requests, new BCrypt hash, and future expiry;
- confirm DB contract for updated credential, reset failed attempts/lock state, and no pending
  reset requests.

The gate also ran Playwright smoke: `6 passed`.

## Risks And Follow-Up

- SMTP delivery remains represented by the Python sender hook. Production email integration should
  be handled with the broader auth/session/runtime configuration cleanup.
- Local register/login/change-password remain Java-owned and should be migrated as a separate auth
  milestone with credential/session parity.
- Bearer-token authentication filters and scope enforcement remain Java-owned despite API token
  management routes being Python-owned.
