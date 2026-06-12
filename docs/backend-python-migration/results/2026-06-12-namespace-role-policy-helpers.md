# Namespace Role Policy Helpers Result

Date: 2026-06-12

## Summary

Milestone 116.4 moved namespace-role normalization and common namespace-role predicates into
`app.auth.policy`.

- Added `namespace_role(...)`, `namespace_role_allows(...)`, `is_namespace_owner(...)`,
  `is_namespace_manager(...)`, `is_namespace_member(...)`, and `managed_namespace_ids(...)`.
- Updated namespace member/profile read and mutation paths to use shared owner/manager/member
  predicates.
- Updated skill lifecycle, promotion workflow, review approval/query, governance workbench,
  security audit, skill label checks, and skill read/detail visibility checks to use shared
  namespace-role helpers.
- Added a static policy-enforcement test so protected modules cannot reintroduce local
  `{"OWNER", "ADMIN"}` namespace-manager predicates silently.
- Updated stale lifecycle hybrid gates to assert `rereleaseBoundaryStillPythonOwned`, matching the
  current Python-owned rerelease route.

## Review Findings

- The first run of `verify-skill-submit-review-smoke` and `verify-skill-lifecycle-archive-smoke`
  showed submit/archive behavior, database state, and audit checks passing, but both failed on the
  old `rereleaseBoundaryJavaOwned` expectation. `server-python/app/api/lifecycle.py` already owns
  rerelease routes in Python, and the Vite proxy returned FastAPI validation status `422` while Java
  returned `401`. The gate expectation was stale and was updated.
- `verify-promotion-read-smoke` showed detail, unauthenticated, and Java-owned write-boundary
  checks passing, but global list comparisons were polluted by pending promotion fixtures from
  prior live gates. The write-path policy touched in this milestone was verified with
  `verify-promotion-submit-reject-smoke`.

## TDD Evidence

Red runs:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Expected failure before helper implementation: namespace-role helpers were not exported from
    `app.auth.policy`.
- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Expected failure after static enforcement was added: governance and review modules still had
    local `{"OWNER", "ADMIN"}` namespace-manager predicates.

Green runs:

- `uv run pytest tests/test_route_policy_enforcement.py -q`
  - Result: 8 passed.
- `uv run pytest tests/test_route_policy_enforcement.py tests/test_namespace_member_read.py tests/test_namespace_member_mutation.py tests/test_namespace_profile_lifecycle.py tests/test_namespace_read.py tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_rerelease.py tests/test_promotion_read.py tests/test_promotion_write.py tests/test_review_list.py tests/test_review_detail.py tests/test_review_skill_detail.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_review_submit.py tests/test_governance_workbench.py tests/test_security_audit.py tests/test_skill_detail.py tests/test_skill_versions.py tests/test_skill_version_detail.py tests/test_skill_label_mutations.py tests/test_labels.py tests/test_skill_tags.py -q`
  - Result: 160 passed, 1 warning.
- `uv run pytest tests/test_hybrid_makefile.py tests/test_route_policy_enforcement.py tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_submit_review.py -q`
  - Result: 27 passed, 1 warning.
- `python -m compileall` on the touched policy, namespace, lifecycle, promotion, review,
  governance, security audit, label, and skill modules.
- `rg` static scan for local namespace-manager role literals in the scoped policy-heavy modules.
  - Result: no matches.

## Live Verification

- `.\scripts\dev-hybrid.ps1 -Action verify-namespace-member-mutation-smoke`
  - Python pytest: 19 passed, 1 warning.
  - Vite proxy regression: 48 passed.
  - Java/Python/proxy member mutation contract checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-review-list-smoke`
  - Python pytest: 25 passed, 1 warning.
  - Java/Python/proxy/proxyWeb review list contract checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-review-approve-smoke`
  - Python pytest: 9 passed, 1 warning.
  - Java/Python/proxy/proxyWeb approve contract, DB, and audit checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-governance-workbench-smoke`
  - Python pytest: 13 passed, 1 warning.
  - Java/Python/proxy governance summary, inbox, activity, and notification checks passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-promotion-submit-reject-smoke`
  - Python pytest: 25 passed, 1 warning.
  - Java/Python/proxy/proxyWeb submit and reject contract, DB, audit, and notification checks
    passed.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-skill-lifecycle-archive-smoke`
  - Python pytest: 11 passed, 1 warning.
  - Java/Python/proxy/proxyWeb archive and unarchive contract, DB, and audit checks passed.
  - `rereleaseBoundaryStillPythonOwned: true`.
  - Playwright smoke: 6 passed.
- `.\scripts\dev-hybrid.ps1 -Action verify-skill-submit-review-smoke`
  - Python pytest: 40 passed, 1 warning.
  - Java/Python/proxy/proxyWeb submit-review contract, DB, and audit checks passed.
  - `rereleaseBoundaryStillPythonOwned: true`.
  - Playwright smoke: 6 passed.

Hybrid scripts reported Windows process-stop warnings for port 8080 during teardown. The gates above
returned exit code 0 after the stale lifecycle boundary expectation was fixed.

## Files Changed

- `server-python/app/auth/policy.py`
- `server-python/app/api/labels.py`
- `server-python/app/api/skills.py`
- `server-python/app/governance/workbench.py`
- `server-python/app/lifecycle/skill.py`
- `server-python/app/namespace/members.py`
- `server-python/app/namespace/mutations.py`
- `server-python/app/namespace/read.py`
- `server-python/app/promotion/workflow.py`
- `server-python/app/review/approval.py`
- `server-python/app/review/query.py`
- `server-python/app/security_audit.py`
- `server-python/tests/test_route_policy_enforcement.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
