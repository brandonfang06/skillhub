# API Token Management Migration Plan

## Summary

Move self-service API token management routes to FastAPI as a cohesive security-boundary
milestone. This migrates token CRUD storage behavior, not the bearer-token authentication filter
or OAuth/device-flow login.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/tokens`
- `GET /api/v1/tokens`
- `DELETE /api/v1/tokens/{id}`
- `PUT /api/v1/tokens/{id}/expiration`

Unchanged:

- `/api/v1/auth/**` except existing `GET /api/v1/auth/me` remains Java-owned.
- `/oauth2/**` remains Java-owned.
- CLI device authorization flow remains Java-owned.
- Bearer-token authentication, token scope filters, and `Authorization: Bearer ...` request
  principal bridging remain Java-owned until a dedicated auth-filter milestone.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/TokenController.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/entity/ApiToken.java`
- `server/skillhub-app/src/test/java/com/iflytek/skillhub/controller/TokenControllerTest.java`
- `server/skillhub-app/src/main/resources/db/migration/V1__init_schema.sql`
- `server/skillhub-app/src/main/resources/db/migration/V8__token_name_constraints.sql`
- `server/skillhub-app/src/main/resources/db/migration/V24__api_token_timestamptz.sql`

Expected behavior:

- Requires an authenticated current user.
- Create:
  - trims token name;
  - rejects blank and names longer than 64 chars;
  - rotates an active same-name token by revoking the old row before inserting the replacement;
  - maps unique-constraint races to `error.token.name.duplicate`;
  - defaults scopes to `["skill:read","skill:publish"]`;
  - stores only SHA-256 token hash and an 8-character token prefix;
  - returns the raw `sk_` token exactly once.
- List:
  - returns only active tokens for the current user;
  - orders by `created_at DESC`;
  - clamps page to at least `0` and size to at least `1`;
  - formats null timestamps as empty strings and UTC timestamps with `Z`.
- Revoke:
  - idempotently revokes only a token owned by the current user;
  - returns HTTP `204` with an empty body.
- Update expiration:
  - updates only active tokens owned by the current user;
  - returns `error.token.notFound` for missing, foreign, or revoked token;
  - accepts `Instant`, offset datetime, and naive local datetime treated as UTC;
  - rejects invalid and non-future expiration values.

## Implementation Scope

Allowed edits:

- `server-python/app/auth/tokens.py`
- `server-python/app/api/tokens.py`
- `server-python/app/main.py`
- `server-python/tests/test_api_tokens.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- OAuth/session/device-flow routes.
- Bearer token authentication filter or scope enforcement.
- Database schema changes.

## Test Plan

- Unit tests:
  - create/rotate stores SHA-256 hash, prefix, scopes, and returns raw token once;
  - list filters active current-user tokens and returns Java-compatible page data;
  - revoke is owner-scoped and idempotent;
  - update expiration validates ownership, revoked state, and timestamp parsing.
- Route tests:
  - routes require `X-Mock-User-Id` current-user bridge;
  - response envelopes match Java messages/shapes;
  - revoke returns `204` empty body.
- Vite tests:
  - all token CRUD routes resolve to Python;
  - unrelated auth/OAuth routes remain Java-owned.
- Windows live gate:
  - Java/Python/proxy contract comparison for create, list, update expiration, revoke,
    invalid expiration, missing token, and unauthenticated cases;
  - DB checks prove raw token is not stored, hash is 64 hex chars, rotate revokes old active row,
    and revoke only affects owner-scoped rows.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_api_tokens.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-api-token-management-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Implement token service and FastAPI routes.
- [x] Move Vite proxy ownership for token routes.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.
