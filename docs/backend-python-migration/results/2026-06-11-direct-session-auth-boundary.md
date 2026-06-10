# Direct And Session Auth Boundary Migration Result

## Summary

Moved the direct-login and session-bootstrap route boundary to FastAPI:

- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/session/bootstrap`

This milestone preserves Java's default-disabled behavior and keeps full cookie/session
persistence as a deferred auth/session replacement task.

## Route Ownership

Before:

- `POST /api/v1/auth/direct/login`: Java
- `POST /api/v1/auth/session/bootstrap`: Java

After:

- `POST /api/v1/auth/direct/login`: Python
- `POST /api/v1/auth/session/bootstrap`: Python

Unchanged:

- `/oauth2/**`: Java
- Device flow, bearer-token authentication filters, scope enforcement, and final session
  persistence: deferred
- Notification SSE: Java

## Implementation Notes

- Direct login now checks the Python `auth_direct_enabled` flag first, matching Java's disabled
  guard ordering.
- Default direct login returns HTTP 403 with `error.auth.direct.disabled`.
- When direct login is enabled, unsupported providers return HTTP 400 with
  `error.auth.direct.providerUnsupported`.
- Enabled direct-local delegates to the migrated local login path and returns the same
  `response.success.read` envelope, but does not create Spring Session rows.
- Session bootstrap now checks the Python `auth_session_bootstrap_enabled` flag first, matching
  Java's disabled guard ordering.
- Default session bootstrap returns HTTP 403 with `error.auth.sessionBootstrap.disabled`.
- When session bootstrap is enabled, unsupported providers return HTTP 400 with
  `error.auth.sessionBootstrap.providerUnsupported`.
- No production Java passive bootstrap provider currently exists; successful bootstrap/session
  persistence remains deferred.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='C:\Users\USER\OneDrive\Documents\skillhub\.uv-cache'; uv run pytest tests/test_direct_session_auth_boundary.py tests/test_auth_method_catalog.py tests/test_hybrid_makefile.py -q`
  - Result: `17 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `38 passed`
- Windows live gate:
  - `powershell -ExecutionPolicy Bypass -File scripts/dev-hybrid.ps1 verify-direct-session-auth-boundary-smoke`
  - Result: passed
  - Java/Python/proxy direct login statuses: `[403, 403, 403]`
  - Java/Python/proxy session bootstrap statuses: `[403, 403, 403]`
  - Playwright smoke: `6 passed`
- Post-gate cleanup check:
  - `netstat -ano | Select-String -Pattern ':3000|:8000|:8080|:8081'`
  - Result: no `LISTEN` rows, only `TIME_WAIT` rows.

## Risks And Follow-Up

- Full cookie/session persistence is not complete. This is consistent with the local auth core
  migration and remains a dedicated final auth/session replacement task.
- Session bootstrap success is not implemented because Java production code has no concrete passive
  authenticator; only the disabled and unsupported-provider boundary is active here.
- OAuth callbacks, device flow, API-token filter auth, and final proxy cleanup remain future work.
