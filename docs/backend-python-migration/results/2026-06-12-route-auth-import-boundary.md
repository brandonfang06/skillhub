# Route Auth Import Boundary Result

Date: 2026-06-12

## Summary

Milestone 116.2 continued the global route-policy cutover by removing the remaining production API
route imports of auth principal helpers from `app.api.auth`.

- All Python API route modules now import `read_current_mock_user` from `app.auth.context`.
- `app.api.auth` remains the auth route module and compatibility facade, but no non-auth API route
  module imports principal helpers from it.
- `app.auth.context` is now the route-facing boundary for mock-user principal reads.
- Social routes are registered before broad lifecycle hard-delete routes so social DELETE paths are
  not captured by `DELETE /api/web/skills/{namespace}/{slug}`.
- Governance workbench live fixture cleanup now removes dependent `skill_search_document` rows and
  stale report-submit fixture rows before recreating governance fixtures.

## Bug Found During Verification

The broader protected-route test cluster exposed that:

- `DELETE /api/web/skills/10/star`
- `DELETE /api/web/skills/10/subscription`

were routed to lifecycle hard-delete instead of social unstar/unsubscribe. The cause was route
registration order: `lifecycle_router` was included before `social_router`, and FastAPI checks
routes in registration order. Moving `social_router` before `lifecycle_router` restores the intended
social route handling.

The governance live gate also exposed two fixture cleanup issues:

- Old governance skills could not be deleted while referenced by `skill_search_document`.
- Old `codex-report-submit-%` report fixtures could make the report inbox comparison pick different
  rows for Java and Python when timestamps tied.

Both were fixed in `scripts/dev-hybrid.ps1` so the governance smoke gate is deterministic.

## Remaining Milestone 116 Work

- Enumerate every protected route and expected principal types.
- Move duplicated role/namespace authorization logic into shared policy helpers.
- Continue behavior-level route-policy coverage for governance, reports, notifications, social,
  namespace, and admin surfaces.

## TDD Evidence

Red run:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Expected failure: 14 API route modules still imported `read_current_mock_user` from
    `app.api.auth`.

Green runs:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
- `python -m compileall server-python\app\api\admin_audit_logs.py server-python\app\api\admin_labels.py server-python\app\api\admin_review_reports.py server-python\app\api\admin_search.py server-python\app\api\admin_skills.py server-python\app\api\admin_users.py server-python\app\api\governance.py server-python\app\api\labels.py server-python\app\api\namespaces.py server-python\app\api\notifications.py server-python\app\api\security_audit.py server-python\app\api\skill_reports.py server-python\app\api\social.py server-python\app\api\user_profile.py`
- `uv run pytest tests/test_skill_star.py::test_skill_star_routes_use_java_envelopes_and_auth_boundaries tests/test_skill_subscription.py::test_skill_subscription_routes_use_java_envelopes_and_auth_boundaries tests/test_final_cutover_baseline.py::test_final_cutover_deferred_categories_are_explicit -q`
- `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_audit_logs.py tests/test_admin_bearer_policy.py tests/test_admin_label_definitions.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py tests/test_admin_search_rebuild.py tests/test_admin_skill_governance.py tests/test_admin_user_management.py tests/test_governance_workbench.py tests/test_labels.py tests/test_skill_label_mutations.py tests/test_namespace_read.py tests/test_namespace_member_read.py tests/test_namespace_member_mutation.py tests/test_namespace_profile_lifecycle.py tests/test_notifications.py tests/test_notification_preferences.py tests/test_notification_sse.py tests/test_security_audit.py tests/test_skill_report_submit.py tests/test_my_social_lists.py tests/test_skill_star.py tests/test_skill_subscription.py tests/test_skill_rating.py tests/test_user_profile.py tests/test_final_cutover_baseline.py tests/test_route_registry.py -q`
  - Result: 137 passed, 1 warning.

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-skill-star-smoke`
  - Python pytest: 15 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite star contract checks passed.
  - Python direct and Vite proxy web unstar routes returned `200`, confirming social routes are not
    captured by lifecycle hard-delete.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-skill-subscription-smoke`
  - Python pytest: 11 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/Vite subscription contract checks passed.
  - Python direct and Vite proxy web unsubscribe routes returned `200`, confirming social routes are
    not captured by lifecycle hard-delete.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-governance-workbench-smoke`
  - First run failed during fixture cleanup because `skill_search_document` still referenced old
    governance skills.
  - Second run reached contract comparison but failed because stale report-submit fixtures made
    `reportInboxEnvelopeMatches` nondeterministic.
  - After fixture cleanup fixes, Python pytest: 13 passed, 1 warning; Vite proxy regression: 48
    passed; Java/Python/Vite governance workbench contract checks passed; Playwright smoke: 6 passed.
- Hybrid scripts reported Windows process-stop warnings for port 8080, but follow-up
  `.\scripts\dev-hybrid.ps1 -Action status` showed Java, Python, and Vite stopped after the gates.

## Files Changed

- `server-python/app/main.py`
- `scripts/dev-hybrid.ps1`
- `server-python/app/api/admin_audit_logs.py`
- `server-python/app/api/admin_labels.py`
- `server-python/app/api/admin_review_reports.py`
- `server-python/app/api/admin_search.py`
- `server-python/app/api/admin_skills.py`
- `server-python/app/api/admin_users.py`
- `server-python/app/api/governance.py`
- `server-python/app/api/labels.py`
- `server-python/app/api/namespaces.py`
- `server-python/app/api/notifications.py`
- `server-python/app/api/security_audit.py`
- `server-python/app/api/skill_reports.py`
- `server-python/app/api/social.py`
- `server-python/app/api/user_profile.py`
- `server-python/tests/test_route_policy_enforcement.py`
- `server-python/tests/test_final_cutover_baseline.py`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
