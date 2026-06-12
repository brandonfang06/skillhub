# Session And OAuth Boundary Foundation Result

Date: 2026-06-12

## Summary

Milestone 115.1 completed the first auth cutover slice.

- Local password login now creates a Python-owned `SESSION` cookie.
- Direct local login reuses the same session creation path when direct auth is enabled.
- `GET /api/v1/auth/me`, `GET /api/v1/whoami`, and `GET /api/cli/v1/auth/whoami` can resolve session-cookie principals after preserving existing `X-Mock-User-Id` and bearer-token precedence.
- `POST /api/v1/auth/logout` invalidates the Python session entry and clears the `SESSION` cookie.
- `/oauth2/authorization/{registrationId}` redirects when a provider registration includes authorization config and preserves sanitized `returnTo` in state.
- `/login/oauth2/code/{registrationId}` rejects missing codes and unknown providers, then can exchange/bind through injectable OAuth abstractions, create the same Python session cookie, and redirect to remembered `returnTo`.

## Remaining 115.2 Work

- Replace the in-process session store with Redis or the selected durable session strategy.
- Load default OAuth provider config from the same environment variables used by the Java backend.
- Implement default provider HTTP token/userinfo exchange.
- Implement default DB identity binding/upsert using the existing `identity_binding`, `user_account`, `namespace_member`, and role tables.
- Add a hybrid live gate for configured OAuth/deferred OAuth paths after the default provider flow exists.

## Java Parity Checklist

| Category | Outcome |
| --- | --- |
| API contract | Covered for local/direct login responses, current-user reads, logout status, OAuth authorization redirect boundary, and OAuth callback boundary errors. |
| Authorization/session behavior | Covered for cookie creation/read/logout and mock-over-bearer-over-session precedence. Durable session storage remains deferred to 115.2. |
| Database transaction atomicity | Not applicable for session-cookie tests. OAuth DB identity binding remains deferred to 115.2. |
| Audit actor/timestamp fields | Not applicable for this foundation slice. |
| Storage and side effects | Not applicable. |
| Live verification evidence | Covered for migrated local-auth route parity through the existing hybrid local-auth smoke gate. Full OAuth live verification remains deferred until default provider exchange and DB binding exist. |

## TDD Evidence

Red runs:

- `uv run pytest tests/test_session_auth.py -q`
  - Expected failures: missing `SESSION` cookie and missing logout route.
- `uv run pytest tests/test_oauth_flow.py -q`
  - Expected failures: OAuth authorization still returned `error.auth.oauth.deferred` and callback route did not exist.

Green runs:

- `uv run pytest tests/test_session_auth.py -q`
- `uv run pytest tests/test_oauth_flow.py tests/test_oauth_boundary.py -q`
- `uv run pytest tests/test_session_auth.py tests/test_oauth_flow.py tests/test_oauth_boundary.py tests/test_auth_method_catalog.py tests/test_local_auth_core.py tests/test_direct_session_auth_boundary.py tests/test_auth_me.py tests/test_auth_bearer.py tests/test_auth_whoami.py -q`
- `uv run pytest tests/test_route_registry.py tests/test_final_cutover_baseline.py -q`

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-local-auth-core-smoke`
  - Python pytest: 19 passed.
  - Vite proxy regression: 48 passed.
  - Hybrid stack started Java, Python, scanner, and Vite successfully.
  - Java/Python/Vite local register/login/change-password contract checks passed.
  - Playwright smoke: 6 passed.
  - Script reported a port-stop warning for Java, but a follow-up `.\scripts\dev-hybrid.ps1 -Action status` showed Java, Python, and Vite stopped; `netstat` showed only `TIME_WAIT` entries for the checked ports.

## Files Changed

- `server-python/app/auth/session.py`
- `server-python/app/api/auth.py`
- `server-python/app/api/local_auth.py`
- `server-python/tests/test_session_auth.py`
- `server-python/tests/test_oauth_flow.py`
- `server-python/tests/test_route_registry.py`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
