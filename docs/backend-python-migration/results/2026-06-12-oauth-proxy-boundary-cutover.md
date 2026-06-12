# OAuth Proxy Boundary Cutover Result

Date: 2026-06-12

## Summary

Moved the OAuth authorization boundary proxy from Java to Python.

- Python now owns `GET /oauth2/authorization/{registrationId}`.
- Known configured providers return `501` with `{"detail":"error.auth.oauth.deferred"}`.
- Unknown providers return `404` with `{"detail":"error.auth.oauth.providerNotFound"}`.
- Vite `/oauth2/**` now targets Python `8081`.
- The Vite dev proxy no longer contains any Java `8080` target.

Full external OAuth provider redirect, callback token exchange, identity binding, and session cookie creation remain deferred.

## Java Parity Checklist

- API contract: covered for the boundary response now owned by Python.
- Authorization/session behavior: deferred. Java still performs the real OAuth redirect/session flow; Python intentionally returns `error.auth.oauth.deferred` until the full session replacement milestone.
- Database transaction atomicity: not applicable.
- Audit actor/timestamp fields: not applicable.
- Storage and side effects: not applicable.
- Live verification evidence: covered.

## Verification

- `uv run pytest tests/test_oauth_boundary.py tests/test_auth_method_catalog.py tests/test_route_registry.py -q`
  - Result: `10 passed, 1 warning`
- `npm.cmd run test -- vite.config.test.ts`
  - Result: `48 passed`
- `rg -n "target:\s*'http://localhost:8080'|toBe\('http://localhost:8080'\)" web\vite.config.ts web\vite.config.test.ts`
  - Result: no matches.
- Hybrid live gate:
  - Python direct known provider: `501`, `{"detail":"error.auth.oauth.deferred"}`
  - Vite proxy known provider: `501`, `{"detail":"error.auth.oauth.deferred"}`
  - Python direct unknown provider: `404`, `{"detail":"error.auth.oauth.providerNotFound"}`
  - Vite proxy unknown provider: `404`, `{"detail":"error.auth.oauth.providerNotFound"}`
  - Java direct known provider: `302`, redirect host `github.com`
  - Vite health proxy: `code = 0`, `data.message = "UP"`

## Files Changed

- `server-python/app/api/auth.py`
- `server-python/tests/test_oauth_boundary.py`
- `server-python/tests/test_route_registry.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-12-oauth-proxy-boundary-cutover.md`
