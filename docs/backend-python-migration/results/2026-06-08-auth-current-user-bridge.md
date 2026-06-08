# Auth Current User Bridge Result

Date: 2026-06-08

## Summary

Migrated `GET /api/v1/auth/me` to FastAPI as the first Group C auth/current-user bridge.

The Python route supports the local development `X-Mock-User-Id` flow and reads active users plus
platform roles from PostgreSQL. It returns the same stable Java contract for deterministic local
users:

- `local-user`
- `local-admin`

Java remains owner for login, OAuth, session bootstrap, API tokens, local auth mutations, ClawHub
whoami, and CLI auth.

## Routes Changed

| Method | Path | Before | After | Notes |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | java | python | Local mock-user current user bridge. |

## Routes Kept Java-Owned

- `GET /api/v1/auth/methods`
- `GET /api/v1/auth/providers`
- `POST /api/v1/auth/session/bootstrap`
- `POST /api/v1/auth/direct/login`
- `/api/v1/auth/local/**`
- `/api/v1/tokens/**`
- `/oauth2/**`
- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`

## Implementation Notes

- Added `server-python/app/api/auth.py`.
- Registered the auth router in `server-python/app/main.py`.
- Added repository and route tests for active users, default `USER` role, unknown/disabled users,
  envelope shape, and 401 behavior.
- Added Vite proxy ownership for `GET /api/v1/auth/me`.
- Added `scripts/dev-hybrid.ps1 verify-auth-me-smoke`.
- Updated Playwright E2E session helper so the local mock-session path keeps
  `X-Mock-User-Id: local-user` on the browser context while this milestone uses a Python mock-user
  auth bridge instead of Java session-cookie reading.

## Live Verification

Command:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-auth-me-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxy: true`
- `noHeaderMatches: true`
- `authMethodsRemainsJava: true`
- Playwright smoke E2E: `6 passed`

Artifact:

- `.dev/auth-me-contract-result.json`

Cleanup check:

- Docker containers: none running.
- Ports `3000`, `8080`, and `8081`: no `LISTENING` entries; only `TIME_WAIT` entries remained.

## Unit And Static Verification

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result:

- `103 passed, 1 warning`

```powershell
cd web
node_modules\.bin\vitest.CMD vite.config.test.ts --run
```

Result:

- `16 passed`

```powershell
cd web
node_modules\.bin\tsc.CMD --noEmit
```

Result:

- exit code `0`

## Issues Found And Fixed

1. Java localized `ok("response.success.read")` to `"获取成功"`, while the first Python
   implementation returned the raw key. The Python route now returns the Java live contract value.
2. Playwright `registerSession` created a Java mock session, but Python-owned `/api/v1/auth/me`
   does not read Java session cookies. The E2E mock-session path now keeps `X-Mock-User-Id:
   local-user` on the browser context.

## Risks

- This milestone is a local mock-user bridge, not a complete Python session/auth replacement.
- Cookie-based Java session login can still be used by Java-owned routes, but Python-owned
  `/api/v1/auth/me` only trusts `X-Mock-User-Id` in this phase.
- Mutating auth, OAuth, token, CLI auth, and CSRF behavior remain deferred.

## Follow-Up

- Decide whether the next Group C milestone should add Python session-cookie compatibility,
  organization identity integration, or viewer-specific role/capability reads.
- If full Playwright E2E is required after more protected routes move to Python, add a broader
  Python auth bridge before relying on Java session cookies.
