# Mutation Transaction Boundaries Result

Date: 2026-06-12

Milestone: Post Python Cutover Hardening Milestone 4

## Scope

This milestone made lifecycle, review, promotion, and publish mutation transaction boundaries explicit without changing public API contracts or state-transition behavior.

## Changes

- Added `server-python/app/db/unit_of_work.py` with `transaction_connection(engine)`, a small wrapper around the existing `engine.begin()` transaction behavior.
- Added `server-python/app/audit/writer.py` for the shared audit-log insert shape used by mutation workflows.
- Updated lifecycle mutation flows in `server-python/app/lifecycle/skill.py` and `server-python/app/lifecycle/hard_delete.py` to use the shared transaction boundary.
- Updated review submit, approve, reject, and withdraw flows in `server-python/app/review/approval.py` to use the shared transaction boundary and audit writer.
- Updated promotion submit, approve, and reject flows in `server-python/app/promotion/workflow.py` to use the shared transaction boundary and audit writer.
- Updated publish write transaction entry points in `server-python/app/publish/orchestration.py` and `server-python/app/publish/transaction.py` to use the shared transaction boundary.
- Updated publish compat audit side effect in `server-python/app/publish/side_effects.py` to use the shared audit writer.
- Added `server-python/tests/test_transaction_boundaries.py` to cover the transaction helper, audit writer insert shape, and null audit-detail preservation.

## Compatibility Notes

- The shared transaction helper delegates to `engine.begin()`, so SQLAlchemy commit and rollback semantics remain unchanged.
- Existing after-commit cleanup and compensation paths still execute outside the main mutation transaction where they did before.
- Audit `detail_json` behavior preserves `NULL` when existing flows pass no detail. A targeted lifecycle test caught an initial `{}` regression, and `test_write_audit_log_preserves_null_detail` now guards this behavior directly.
- Publish scanner handoff and search document updates were not moved across transaction boundaries; the change only makes the DB transaction entry point explicit.

## Verification

- `cd server-python; uv run pytest tests/test_transaction_boundaries.py tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_rerelease.py tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_hard_delete.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_review_submit.py tests/test_promotion_write.py tests/test_publish_orchestration.py tests/test_publish_transaction.py tests/test_publish_storage.py tests/test_publish_side_effects.py -q`
  - Result: `108 passed, 1 warning`
- `cd server-python; uv run pytest tests -q`
  - Result: `718 passed, 1 warning`
- `cd web; corepack pnpm run test:e2e:smoke`
  - Result: `6 passed`

## Residual Risk

- `server-python/app/audit/writer.py` centralizes the common audit insert shape, but other admin and profile modules still own their local audit insert SQL. Those paths were outside this mutation-boundary milestone.
- ORM mapping has not been introduced yet. Milestone 5 remains the planned point for selective ORM adoption.
