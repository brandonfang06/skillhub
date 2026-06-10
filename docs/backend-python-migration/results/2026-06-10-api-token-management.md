# API Token Management Migration Result

## Summary

Moved self-service API token management routes to FastAPI:

- `POST /api/v1/tokens`
- `GET /api/v1/tokens`
- `DELETE /api/v1/tokens/{id}`
- `PUT /api/v1/tokens/{id}/expiration`

Bearer-token authentication, token scope filters, OAuth, sessions, and CLI device flow remain
Java-owned.

## Changes

- Added Python token service in `server-python/app/auth/tokens.py`.
- Added FastAPI routes in `server-python/app/api/tokens.py`.
- Registered token router in `server-python/app/main.py`.
- Moved Vite dev proxy ownership for `/api/v1/tokens` and child paths to Python.
- Added Windows live gate target:
  `verify-api-token-management-smoke`.
- Updated route ownership documentation and migration sequence.

## Behavior Preserved

- Requires the current-user bridge.
- Create trims and validates token names.
- Create uses Java route semantics: active same-name token is revoked before inserting the
  replacement.
- Default scopes remain `["skill:read","skill:publish"]`.
- Raw `sk_` token is returned once and is not stored.
- Stored token hash is 64-character SHA-256 hex.
- List returns only active owner-scoped tokens, ordered by `created_at DESC`, with page envelope.
- Revoke is owner-scoped and idempotent, returning HTTP `204` with an empty body.
- Expiration update is owner-scoped, active-token only, and accepts Java-compatible timestamp forms.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_api_tokens.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-api-token-management-smoke
```

Results:

- Python narrow tests: `10 passed`.
- Vite proxy tests: `35 passed`.
- Windows live gate:
  - Java/Python/proxy create envelopes matched after stabilizing generated token fields.
  - Java/Python/proxy list envelopes matched.
  - Java/Python/proxy expiration update envelopes matched.
  - Invalid expiration status parity: Java/Python/proxy `400`.
  - Missing update status parity: Java/Python/proxy `404`.
  - Unauthenticated status parity: Java/Python/proxy `401`.
  - Revoke status parity: Java/Python/proxy `204`.
  - DB contract passed for Java/Python/proxy: raw token not stored, hash length 64, hash is hex
    SHA-256, same-name rotation revoked old row, and final revoke left no active row.
  - Playwright smoke: `6 passed`.

## Notes And Risks

- This milestone does not migrate request authentication by bearer token. Existing Java filters
  remain the authority for `Authorization: Bearer ...` behavior and token scope enforcement.
- API token management now uses the Python current-user bridge during hybrid development. A later
  auth-filter milestone must decide how Python validates bearer tokens for non-browser clients.
- The live gate initially exposed a fixture quoting issue for JSONB seed data through
  PowerShell/docker/psql; fixture setup now uses `jsonb_build_array(...)` to avoid shell quote
  mutation.
