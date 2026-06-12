# Global Route Policy Cutover

Date: 2026-06-12

Milestone 116.5 completed the remaining protected-route principal cutover for the Python backend.
Route modules that still resolved only `X-Mock-User-Id` locally now delegate current-principal
resolution to `app.auth.context.resolve_current_user_or_401`.

## Scope

- Account merge, admin audit/search/skill/user/review-report, governance, and user profile routes
  now use the shared resolver.
- Device authorization, skill reports, security audit, labels, notifications, and social routes now
  use the shared resolver.
- Lifecycle, promotion, and review workflow route modules no longer keep `_require_mock_user`
  helpers.
- `app.auth.context` owns the route-unit mock fallback for tests that instantiate `create_app()`
  without lifespan-managed database state. Production/runtime apps still use configured
  `auth_me_reader` or a real `db_engine` for mock-user lookup.

## Guardrails

- `tests/test_route_policy_enforcement.py` now statically rejects `read_current_mock_user`,
  `read_mock_user_or_401`, and workflow `_require_mock_user` usage in the protected API route
  modules covered by this milestone.
- The guardrail keeps `app.api.auth` as the only allowed compatibility wrapper location for legacy
  auth helper exports.

## Verification

All commands ran from `server-python` unless noted.

- `uv run pytest tests/test_route_policy_enforcement.py::test_remaining_user_action_routes_use_shared_principal_resolver -q`
  - Red before implementation, then passed.
- `uv run pytest tests/test_route_policy_enforcement.py::test_workflow_route_modules_use_shared_principal_resolver -q`
  - Red before implementation, then passed.
- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - `13 passed`
- Targeted protected-route suites:
  - `tests/test_device_auth.py`
  - `tests/test_skill_report_submit.py`
  - `tests/test_security_audit.py`
  - `tests/test_notifications.py`
  - `tests/test_notification_sse.py`
  - `tests/test_notification_sse_fanout.py`
  - `tests/test_notification_preferences.py`
  - `tests/test_labels.py`
  - `tests/test_skill_label_mutations.py`
  - `tests/test_my_social_lists.py`
  - Result: `43 passed, 1 warning`
- Targeted lifecycle/promotion/review suites:
  - `tests/test_promotion_write.py`
  - `tests/test_promotion_read.py`
  - `tests/test_review_submit.py`
  - `tests/test_review_skill_detail.py`
  - `tests/test_review_reject_withdraw.py`
  - `tests/test_review_list.py`
  - `tests/test_review_file_content.py`
  - `tests/test_review_download.py`
  - `tests/test_review_detail.py`
  - `tests/test_review_approve.py`
  - `tests/test_skill_lifecycle_withdraw_review.py`
  - `tests/test_skill_lifecycle_submit_review.py`
  - `tests/test_skill_lifecycle_rerelease.py`
  - `tests/test_skill_lifecycle_delete_version.py`
  - `tests/test_skill_lifecycle_confirm_publish.py`
  - `tests/test_skill_lifecycle_archive.py`
  - `tests/test_final_lifecycle_governance_audit.py`
  - Result: `113 passed, 1 warning`
- Full Python backend suite:
  - `uv run pytest tests -q`
  - `709 passed, 1 warning`

## Remaining Risk

- No Java source was changed. Java remains reference-only after Milestone 120.
- This milestone did not broaden API-token bearer access for browser/admin-only routes beyond the
  scope-specific policies already completed in earlier Milestone 116 slices.
