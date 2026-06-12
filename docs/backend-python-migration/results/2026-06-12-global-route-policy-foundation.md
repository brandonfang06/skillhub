# Global Route Policy Foundation Result

Date: 2026-06-12

## Summary

Milestone 116.1 completed the first route-policy cutover slice. Python now has shared auth-layer
helpers for current-principal resolution and API-token route policy checks, and the high-risk route
modules no longer import the private `app.api.auth._read_current_user_or_401` helper.

- `app.auth.context` owns mock-user, bearer API-token, and session-cookie principal resolution.
- `app.auth.policy` owns initial API-token policy checks:
  - required bearer scope checks for API-token principals.
  - unsupported API-token principal rejection for admin/web-only routes.
- `app.api.auth` remains as the public auth route module and keeps small compatibility wrappers for
  tests/imports, but SQL-backed principal reads moved out of the API layer.
- Token, publish, hard-delete, and admin bearer policy routes now call the shared auth helpers.
- Account merge and device authorization now call the shared mock-user boundary instead of importing
  private API helpers.
- `app.auth.local` no longer imports role normalization from `app.api.auth`, avoiding auth-to-API
  dependency direction.

## Remaining Milestone 116 Work

- Enumerate every protected Python route and expected principal types.
- Extend policy helpers to platform-role and namespace-role authorization where route-local logic
  still exists.
- Continue replacing route-local auth imports in governance, report, social, notification, and other
  authenticated route modules.
- Add full invalid-bearer `401`, mock-precedence, session-cookie, and unsupported-bearer route tests
  across the remaining protected surface.

## Java Parity Checklist

| Category | Outcome |
| --- | --- |
| API contract | Covered for the touched route-policy helper behavior; no response schema changes were intended. |
| Authorization/session behavior | Covered for mock/bearer/session resolver precedence and initial API-token scope/admin rejection helpers. Broader role/namespace policy remains in milestone 116. |
| Database transaction atomicity | Not changed; SQL principal reads were moved without changing transaction scope. |
| Audit actor/timestamp fields | Not changed. |
| Storage and side effects | Not applicable. |
| Live verification evidence | Covered by API-token management, publish, and hard-delete hybrid smoke gates across Java, Python, and Vite proxy. |

## TDD Evidence

Red run:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Expected failures: route modules still imported `app.api.auth._read_current_user_or_401`;
    `app.auth.policy` did not exist.

Green runs:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
- `python -m compileall server-python\app\auth\context.py server-python\app\auth\policy.py server-python\app\api\auth.py server-python\app\api\admin_policy.py server-python\app\api\tokens.py server-python\app\api\publish.py server-python\app\api\lifecycle.py`
- `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_bearer_policy.py tests/test_admin_search_rebuild.py tests/test_admin_label_definitions.py tests/test_api_tokens.py tests/test_publish_http_validate.py tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_auth_me.py tests/test_auth_whoami.py tests/test_session_auth.py tests/test_route_registry.py tests/test_final_cutover_baseline.py -q`
  - Result: 73 passed, 1 warning.

## Time-Drift Test Fix

The expanded test run exposed a stale fixed date in `tests/test_api_tokens.py`
(`2026-06-11T12:00:00`), which became invalid on 2026-06-12 because token expirations must be in
the future. The test now uses a dynamic future timestamp while keeping the production validation
unchanged.

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-api-token-scope-smoke`
  - Python pytest: 19 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite API-token scope contract checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-publish-token-scope-smoke`
  - Python pytest: 25 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite publish API-token scope contract checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-hard-delete-token-scope-smoke`
  - Python pytest: 18 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite hard-delete API-token scope contract checks passed.
  - Playwright smoke: 6 passed.
- Each hybrid script reported a Windows process-stop warning for port 8080, but follow-up
  `.\scripts\dev-hybrid.ps1 -Action status` showed Java, Python, and Vite stopped after the gates.

## Files Changed

- `server-python/app/auth/context.py`
- `server-python/app/auth/policy.py`
- `server-python/app/api/auth.py`
- `server-python/app/api/admin_policy.py`
- `server-python/app/api/tokens.py`
- `server-python/app/api/publish.py`
- `server-python/app/api/lifecycle.py`
- `server-python/app/api/account_merge.py`
- `server-python/app/api/device_auth.py`
- `server-python/app/auth/local.py`
- `server-python/tests/test_route_policy_enforcement.py`
- `server-python/tests/test_api_tokens.py`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
