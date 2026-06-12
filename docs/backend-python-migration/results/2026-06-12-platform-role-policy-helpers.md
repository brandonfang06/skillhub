# Platform Role Policy Helpers Result

Date: 2026-06-12

## Summary

Milestone 116.3 moved platform-role normalization and simple route-level platform-role guards into
`app.auth.policy`.

- Added `platform_roles(user)` for deterministic platform-role normalization.
- Added `require_platform_role(...)` and `require_any_platform_role(...)` for route-level guards
  that preserve each route's existing Java-compatible 403 detail string.
- Updated admin search, admin label definitions, admin skill governance, admin users, audit logs,
  and admin review/report routes to use shared platform-role extraction or guards.
- Updated labels, lifecycle hard delete, namespaces, publish, security audit, and social list routes
  to use shared platform-role extraction.
- Kept service-layer business authorization in the existing domain/application services; this slice
  only moved route-level extraction and simple route guards.

## Remaining Milestone 116 Work

- Add namespace-role helpers in `app.auth.policy`.
- Enumerate protected routes and expected principal types.
- Continue moving namespace/member/owner policy checks out of route modules where they are still
  route-local.

## TDD Evidence

Red run:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Expected failure: `platform_roles`, `require_platform_role`, and `require_any_platform_role`
    were not exported from `app.auth.policy`.

Green runs:

- `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_search_rebuild.py tests/test_admin_label_definitions.py tests/test_admin_audit_logs.py tests/test_admin_skill_governance.py tests/test_admin_user_management.py -q`
  - Result: 34 passed, 1 warning.
- `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_search_rebuild.py tests/test_admin_label_definitions.py tests/test_admin_audit_logs.py tests/test_admin_skill_governance.py tests/test_admin_user_management.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py -q`
  - Result: 44 passed, 1 warning.
- `uv run pytest tests/test_route_policy_enforcement.py tests/test_labels.py tests/test_skill_label_mutations.py tests/test_skill_hard_delete.py tests/test_namespace_read.py tests/test_namespace_member_read.py tests/test_namespace_member_mutation.py tests/test_namespace_profile_lifecycle.py tests/test_publish_http_validate.py tests/test_publish_dry_run.py tests/test_security_audit.py tests/test_my_social_lists.py tests/test_skill_star.py tests/test_skill_subscription.py tests/test_skill_rating.py -q`
  - Result: 99 passed, 1 warning.
- `python -m compileall` on the touched route modules and `app.auth.policy`.

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-admin-label-definition-smoke`
  - Python pytest: 11 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite admin label definition contract checks passed, including SUPER_ADMIN-only
    forbidden status behavior.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-admin-user-management-smoke`
  - Python pytest: 12 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite admin user management contract checks passed, including USER_ADMIN role
    extraction and non-admin forbidden behavior.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-publish-http-validate-smoke`
  - Python pytest: 82 passed, 1 warning.
  - Java/Python/Vite publish validate contract checks passed for status, code, validity, warnings,
    errors, resolved slug, and resolved version.
  - Playwright smoke: 6 passed.
- Hybrid scripts reported Windows process-stop warnings for port 8080, but follow-up
  `.\scripts\dev-hybrid.ps1 -Action status` showed Java, Python, and Vite stopped after the gates.

## Files Changed

- `server-python/app/auth/policy.py`
- `server-python/app/api/admin_audit_logs.py`
- `server-python/app/api/admin_labels.py`
- `server-python/app/api/admin_review_reports.py`
- `server-python/app/api/admin_search.py`
- `server-python/app/api/admin_skills.py`
- `server-python/app/api/admin_users.py`
- `server-python/app/api/labels.py`
- `server-python/app/api/lifecycle.py`
- `server-python/app/api/namespaces.py`
- `server-python/app/api/publish.py`
- `server-python/app/api/security_audit.py`
- `server-python/app/api/social.py`
- `server-python/tests/test_route_policy_enforcement.py`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
