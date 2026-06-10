# Direct And Session Auth Boundary Migration Plan

## Summary

Move the default-disabled direct-login and passive session-bootstrap endpoints to FastAPI:

- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/session/bootstrap`

This is a boundary milestone, not the final auth/session replacement. Java defaults both features
to disabled. This milestone preserves that default behavior and moves route ownership so the
remaining auth surface can be isolated behind Python before the final proxy cleanup.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/session/bootstrap`

Unchanged ownership:

- `POST /api/v1/auth/local/register`, `POST /api/v1/auth/local/login`, and
  `POST /api/v1/auth/local/change-password` are already Python-owned.
- `GET /api/v1/auth/providers`, `GET /api/v1/auth/methods`, `GET /api/v1/auth/me`,
  `GET /api/v1/whoami`, and `GET /api/cli/v1/auth/whoami` are already Python-owned.
- `/oauth2/**` remains Java-owned.
- OAuth callbacks, device flow, bearer-token authentication filters, scope enforcement, and final
  cookie/session establishment remain deferred.
- Notification SSE remains Java-owned.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/AuthController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/DirectAuthService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SessionBootstrapService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/config/DirectAuthProperties.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/config/AuthSessionBootstrapProperties.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/direct/LocalDirectAuthProvider.java`

Expected default behavior:

- Direct login is disabled unless `skillhub.auth.direct.enabled` is explicitly true.
- Session bootstrap is disabled unless `skillhub.auth.session-bootstrap.enabled` is explicitly true.
- When disabled, Java checks the disabled flag before provider lookup:
  - direct login returns HTTP 403 with `error.auth.direct.disabled`;
  - session bootstrap returns HTTP 403 with `error.auth.sessionBootstrap.disabled`.
- `POST /api/v1/auth/direct/login` payload shape is `{ provider, username, password }`.
- `POST /api/v1/auth/session/bootstrap` payload shape is `{ provider }`.

Enabled-mode note:

- Java establishes a Spring web session for successful direct login or passive bootstrap.
- Python local login currently preserves the response/database contract but not Spring Session rows.
- This milestone does not claim enabled direct/session parity. Enabled direct login may be wired only
  if it can reuse the migrated local login response safely, but cookie/session persistence remains a
  later auth/session replacement milestone.

## Implementation Scope

Allowed edits:

- `server-python/app/api/auth.py`
- `server-python/tests/test_direct_session_auth_boundary.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Java Flyway schema edits.
- OAuth callback, device-flow, bearer-token filter, or scope enforcement behavior changes.
- Generated OpenAPI TypeScript edits.
- Frontend page/client behavior changes.

## Test Plan

- Python route tests:
  - default direct login returns HTTP 403 and `error.auth.direct.disabled`;
  - default session bootstrap returns HTTP 403 and `error.auth.sessionBootstrap.disabled`;
  - enabled direct login rejects unsupported providers with `error.auth.direct.providerUnsupported`;
  - enabled session bootstrap rejects unsupported providers with
    `error.auth.sessionBootstrap.providerUnsupported`;
  - direct local enabled path, if implemented, delegates to the migrated local login handler and
    returns the Java-compatible success envelope.
- Vite tests:
  - direct login and session bootstrap route to Python before `/api`;
  - `/oauth2/**` remains Java-owned.
- Windows live gate:
  - compare Java/Python/proxy HTTP status for default-disabled direct login and session bootstrap;
  - require all three to return 403.

## Acceptance Criteria

- `cd server-python; uv run pytest tests/test_direct_session_auth_boundary.py tests/test_auth_method_catalog.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell -ExecutionPolicy Bypass -File scripts/dev-hybrid.ps1 verify-direct-session-auth-boundary-smoke`
- `git diff --name-only -- server` prints nothing.
- Result doc records route ownership, verification commands, risks, and follow-up.
