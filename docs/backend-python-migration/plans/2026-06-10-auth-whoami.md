# Auth Whoami Migration Plan

## Summary

Move current-principal whoami read routes to FastAPI:

- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`

These routes read the authenticated principal only. They do not authenticate credentials, establish
sessions, issue tokens, or enforce token scopes.

## Route Ownership

Python-owned after this milestone:

- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`

Unchanged Java-owned routes:

- bearer-token authentication and scope enforcement
- API token authentication filters
- `POST /api/v1/auth/session/bootstrap`
- `POST /api/v1/auth/direct/login`
- `POST /api/v1/auth/local/register`
- `POST /api/v1/auth/local/login`
- `POST /api/v1/auth/local/change-password`
- `/oauth2/**`

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/dto/ClawHubWhoamiResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/cli/CliAuthController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/cli/CliWhoAmIResponse.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/mock/MockAuthFilter.java`

Expected behavior:

- `GET /api/v1/whoami` returns plain ClawHub JSON, not `ApiResponse`:
  `{ "user": { "handle": userId, "displayName": displayName, "image": avatarUrl } }`.
- `GET /api/cli/v1/auth/whoami` returns Java `ApiResponse` envelope with:
  `{ "handle": userId, "displayName": displayName, "email": email }`.
- Both routes require an authenticated principal. During the migration bridge, Python uses the same
  local `X-Mock-User-Id` bridge and active-user lookup as `/api/v1/auth/me`.

## Implementation Scope

Allowed edits:

- `server-python/app/api/auth.py`
- `server-python/tests/test_auth_whoami.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- API token authentication filters or scope enforcement.
- OAuth/session/direct login/local credential flows.
- Database schema changes.

## Test Plan

- Unit/route tests:
  - ClawHub whoami returns plain JSON with handle/displayName/image.
  - CLI whoami returns Java envelope with handle/displayName/email.
  - missing/blank/unknown mock user returns `401`.
- Vite tests:
  - both whoami routes route to Python;
  - direct login/session/bootstrap/OAuth remain Java-owned.
- Windows live gate:
  - Java/Python/proxy compare both routes for `local-user` and `local-admin`;
  - missing auth status is consistent across Java/Python/proxy.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_auth_whoami.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-auth-whoami-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Implement whoami builders and FastAPI routes.
- [x] Move Vite proxy ownership for whoami routes only.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [ ] Commit and push to `origin/dev`.
