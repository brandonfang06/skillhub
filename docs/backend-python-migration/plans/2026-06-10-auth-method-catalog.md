# Auth Method Catalog Migration Plan

## Summary

Move public auth catalog read routes to FastAPI:

- `GET /api/v1/auth/providers`
- `GET /api/v1/auth/methods`

These routes only describe available browser/direct/bootstrap authentication options. They do not
authenticate users, establish sessions, issue tokens, or handle OAuth callbacks.

## Route Ownership

Python-owned after this milestone:

- `GET /api/v1/auth/providers`
- `GET /api/v1/auth/methods`

Unchanged Java-owned routes:

- `GET /api/v1/auth/me`
- `POST /api/v1/auth/session/bootstrap`
- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`
- `/oauth2/**`
- bearer-token authentication and scope enforcement

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/AuthController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/AuthMethodCatalog.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AuthMethodResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AuthProviderResponse.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/oauth/OAuthLoginRedirectSupport.java`
- `server/skillhub-app/src/main/resources/application.yml`

Expected behavior:

- `providers` returns OAuth registrations sorted by registration id.
- Provider name uses configured `client-name`, falling back to id.
- Provider authorization URL is `/oauth2/authorization/{id}` and includes URL-encoded `returnTo`
  only when `returnTo` is a safe relative path.
- `methods` always starts with local password:
  `{ id: "local-password", methodType: "PASSWORD", provider: "local", displayName: "Local Account", actionUrl: "/api/v1/auth/local/login" }`.
- `methods` appends OAuth methods sorted by registration id.
- Direct password and session-bootstrap methods remain disabled by default and are only listed
  when explicitly enabled.

## Implementation Scope

Allowed edits:

- `server-python/app/api/auth.py`
- `server-python/app/core/config.py`
- `server-python/tests/test_auth_method_catalog.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Auth session bootstrap, direct login, local register/login/change-password.
- OAuth callback/authorization route handling.
- Bearer-token authentication and scope enforcement.
- Database schema changes.

## Test Plan

- Unit tests:
  - provider catalog sorting, display-name fallback, and authorization URL generation;
  - safe and unsafe `returnTo` handling;
  - method catalog local-password first, OAuth sorted, direct disabled by default, optional direct local.
- Route tests:
  - `/api/v1/auth/providers` and `/api/v1/auth/methods` return Java-style envelopes.
- Vite tests:
  - providers/methods route to Python;
  - direct login, session bootstrap, local login/register/change-password, and OAuth remain Java-owned.
- Windows live gate:
  - Java/Python/proxy compare providers with and without safe `returnTo`;
  - Java/Python/proxy compare methods with and without safe `returnTo`;
  - invalid `returnTo` is ignored consistently.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_auth_method_catalog.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-auth-method-catalog-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Implement auth catalog helpers and FastAPI routes.
- [x] Move Vite proxy ownership for providers/methods only.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [ ] Commit and push to `origin/dev`.
