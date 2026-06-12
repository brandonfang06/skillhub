# Session And OAuth Completion Result

Date: 2026-06-12

## Summary

Milestone 115.2 completed the Python-owned OAuth/session code path needed to remove Spring Security from the active backend boundary.

- OAuth provider registrations now load Java-compatible GitHub/GitLab environment variables:
  - `OAUTH2_GITHUB_CLIENT_ID`
  - `OAUTH2_GITHUB_CLIENT_SECRET`
  - `OAUTH2_GITLAB_CLIENT_ID`
  - `OAUTH2_GITLAB_CLIENT_SECRET`
  - `OAUTH2_GITLAB_BASE_URI`
  - `OAUTH2_GITLAB_DISPLAY_NAME`
  - `SKILLHUB_PUBLIC_BASE_URL`
- Complete OAuth registrations redirect to provider authorization URLs; incomplete local-dev registrations keep deterministic `error.auth.oauth.deferred`.
- OAuth callbacks now have a default provider token/userinfo exchange helper, plus injectable test seams.
- OAuth claims bind or create users through `identity_binding` and `user_account`, update existing bindings, ensure `@global` namespace membership for new active users, and return Java-compatible principal fields.
- Local/direct/OAuth logins share the same Python `SESSION` cookie path.
- Session storage now has a Redis-compatible store hook with the in-process fallback retained for no-Redis unit tests.

## Operational Gate

External-provider live verification still requires real GitHub/GitLab OAuth client credentials. That is now an operator credential/configuration gate, not a remaining Java runtime dependency. Unit tests cover configured, deferred, default exchange, identity binding, session, and proxy-regression behavior.

## Java Parity Checklist

| Category | Outcome |
| --- | --- |
| API contract | Covered for local/direct login, current-principal reads, logout, OAuth authorization redirect/deferred behavior, and OAuth callback error/success paths. |
| Authorization/session behavior | Covered for `SESSION` cookie creation/read/logout and mock/bearer/session precedence. Redis-compatible storage is available by injection; no-Redis tests keep the fallback. |
| Database transaction atomicity | Covered for OAuth bind/create/update inside `engine.begin()`. |
| Audit actor/timestamp fields | Not applicable; Java OAuth login does not emit a route audit entry in this boundary. |
| Storage and side effects | Not applicable. |
| Live verification evidence | Existing hybrid auth catalog smoke passed for Java/Python/Vite route parity. External provider live verification awaits real OAuth credentials. |

## TDD Evidence

Red runs:

- `uv run pytest tests/test_oauth_flow.py tests/test_session_auth.py -q`
  - Expected failure: `RedisSessionStore` import missing.
- `uv run pytest tests/test_oauth_flow.py tests/test_session_auth.py -q`
  - Expected failures after Redis store: env-based OAuth authorization still returned `501`; default callback still returned `501`.

Green runs:

- `uv run pytest tests/test_oauth_flow.py tests/test_session_auth.py -q`
- `uv run pytest tests/test_session_auth.py tests/test_oauth_flow.py tests/test_oauth_boundary.py tests/test_auth_method_catalog.py tests/test_local_auth_core.py tests/test_direct_session_auth_boundary.py tests/test_auth_me.py tests/test_auth_bearer.py tests/test_auth_whoami.py tests/test_route_registry.py tests/test_final_cutover_baseline.py -q`

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-auth-method-catalog-smoke`
  - Python pytest: 12 passed.
  - Vite proxy regression: 48 passed.
  - Hybrid stack started Java, Python, scanner, and Vite successfully.
  - Java/Python/Vite auth provider and method catalog checks passed for no `returnTo`, safe `returnTo`, and unsafe `returnTo`.
  - Playwright smoke: 6 passed.
  - Script reported a port-stop warning for Java, but a follow-up `.\scripts\dev-hybrid.ps1 -Action status` showed Java, Python, and Vite stopped; `netstat` showed only `TIME_WAIT` entries for the checked ports.

## Files Changed

- `server-python/app/auth/oauth.py`
- `server-python/app/auth/session.py`
- `server-python/app/api/auth.py`
- `server-python/tests/test_oauth_flow.py`
- `server-python/tests/test_session_auth.py`
- `server-python/tests/test_route_registry.py`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
