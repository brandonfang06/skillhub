# Auth Whoami Migration Result

## Summary

Moved current-principal whoami read routes to FastAPI:

- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`

The milestone keeps credential authentication, bearer-token filters, scope enforcement, OAuth,
session bootstrap, direct login, and local register/login/change-password Java-owned.

## Route Ownership

Before:

- `GET /api/v1/whoami` -> Java
- `GET /api/cli/v1/auth/whoami` -> Java

After:

- `GET /api/v1/whoami` -> Python
- `GET /api/cli/v1/auth/whoami` -> Python

## Java Parity

- ClawHub whoami returns plain JSON, not `ApiResponse`:
  `{ "user": { "handle": userId, "displayName": displayName, "image": avatarUrl } }`.
- CLI whoami returns the Java `ApiResponse` envelope with:
  `{ "handle": userId, "displayName": displayName, "email": email }`.
- Missing auth returns `401` for Java, Python, and Vite proxy on both routes.
- Live comparison covered `local-user` and `local-admin` for Java/Python/proxy JSON equality.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_auth_whoami.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-auth-whoami-smoke
```

Results:

- Python route/hybrid-script tests: `10 passed, 1 warning`.
- Vite proxy tests: `37 passed`.
- Windows live gate: passed.
- Playwright smoke inside live gate: `6 passed`.

Live gate artifact:

- `.dev/auth-whoami-contract-result.json`

## Risks And Follow-Up

- This milestone uses the existing local `X-Mock-User-Id` bridge. It does not replace Java bearer
  token authentication or scope enforcement.
- Broader auth surfaces remain Java-owned until explicitly migrated:
  local register/login/change-password, direct login, session bootstrap, OAuth, device flow, and
  bearer-token authentication filters.
