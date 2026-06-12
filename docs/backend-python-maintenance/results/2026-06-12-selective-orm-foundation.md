# Selective ORM Foundation Result

Date: 2026-06-12

Milestone: Post Python Cutover Hardening Milestone 5

## Scope

This milestone introduced SQLAlchemy ORM deliberately for mutation-heavy aggregate tables only. It did not convert projection-heavy read repositories or rewrite lifecycle/review/promotion business flows.

## Changes

- Added `server-python/app/db/models.py` with declarative mappings for:
  - `skill`
  - `skill_version`
  - `review_task`
  - `promotion_request`
  - `namespace`
  - `namespace_member`
  - `user_account`
  - `api_token`
  - `audit_log`
- Added `server-python/app/db/session.py` with `create_sessionmaker(engine)` for binding SQLAlchemy async sessions to the existing async engine.
- Added `server-python/tests/test_orm_mapping.py` covering mapped table names, primary keys, important mutation/status columns, basic insert/load behavior, session factory binding, and module containment.
- Updated `server-python/tests/test_post_cutover_architecture.py` so ORM is allowed only in `app/db/models.py`; future scattered ORM declarations fail the guardrail.
- Converted the shared audit writer to use `insert(AuditLog)` instead of raw `text()` SQL. This gives the lifecycle/review/promotion/publish mutation paths their first low-risk ORM-backed write helper through the existing public `write_audit_log` function.

## Compatibility Notes

- Existing lifecycle, review, promotion, and publish functions still keep their SQL and transaction behavior from Milestone 4.
- Read repositories from Milestones 2 and 3 remain explicit SQL.
- The ORM mappings intentionally omit relationships for now. This keeps the first foundation small and avoids accidental lazy-load behavior in async paths.
- JSON columns use SQLAlchemy `JSON` for mapping portability. The deployed PostgreSQL schema remains the source of truth for JSONB storage.
- The `audit_log.detail_json` `NULL` behavior from Milestone 4 remains covered by `test_write_audit_log_preserves_null_detail`.

## Verification

- `cd server-python; uv run pytest tests/test_orm_mapping.py tests/test_post_cutover_architecture.py tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_confirm_publish.py tests/test_review_approve.py tests/test_promotion_write.py tests/test_publish_orchestration.py tests/test_transaction_boundaries.py -q`
  - Result: `47 passed, 1 warning`
- `cd server-python; uv run pytest tests -q`
  - Result: `723 passed, 1 warning`
- `cd web; corepack pnpm run test:e2e:smoke`
  - Result: `6 passed`
- `git diff --check`
  - Result: no whitespace errors; PowerShell reported only CRLF working-copy warnings.

## Residual Risk

- Main mutation workflows are not yet fully ORM-based. This milestone establishes the mapped foundation and one low-risk mapped insert; broader conversion should remain incremental and test-first.
- ORM mappings are intentionally limited to the selected mutation aggregate tables. Projection/search/report tables are still explicit SQL by design.
