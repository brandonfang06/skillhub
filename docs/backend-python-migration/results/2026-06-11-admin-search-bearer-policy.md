# Admin Search Bearer Policy Migration Result

## Summary

Aligned the already Python-owned admin search rebuild route with Java API-token route policy:

- `POST /api/v1/admin/search/rebuild`

The route still uses `X-Mock-User-Id` as the supported local admin identity path. Valid bearer
API-token principals without a mock user now receive Java-compatible unsupported endpoint behavior.

## Behavior

- Missing auth: `401 error.auth.required`
- Invalid bearer token: `401 error.auth.required`
- Valid bearer API token: `403 API token cannot access endpoint: /api/v1/admin/search/rebuild`
- Mock user plus bearer token: mock-user precedence, preserving local development behavior
- Super-admin mock user: rebuild behavior unchanged

## Verification

- `uv run pytest tests/test_admin_search_rebuild.py -q`
  - Result: `4 passed, 1 warning`
- `uv run pytest tests/test_admin_search_rebuild.py tests/test_route_registry.py -q`
  - Result: `6 passed, 1 warning`
- `npm.cmd run test -- vite.config.test.ts`
  - Result: `47 passed`
- Manual hybrid live gate:
  - Created a Java API token with `skill:read`, `skill:publish`, `skill:delete`, and
    `token:manage` scopes.
  - Java direct `POST /api/v1/admin/search/rebuild` with bearer token: `403`
  - Python direct `POST /api/v1/admin/search/rebuild` with bearer token: `403`
  - Vite proxy `POST /api/v1/admin/search/rebuild` with bearer token: `403`
  - Python invalid bearer token: `401 error.auth.required`
  - Python mock user plus bearer token: `200`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 status`
  after shutdown:
  - Result: Java, Python, and Vite stopped; Docker services removed.
- `git diff --check`
  - Result: passed with CRLF conversion warnings only.
- `git diff --name-only -- server`
  - Result: no output.

## Follow-Up

This is a narrow route-policy slice. Other authenticated Python-owned routes that still only accept
the mock-user bridge should get the same Java-compatible bearer unsupported handling before final
proxy cleanup.
