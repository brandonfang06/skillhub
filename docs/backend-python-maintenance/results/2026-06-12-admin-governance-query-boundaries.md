# Admin Governance Query Boundaries Result

Date: 2026-06-12

Milestone: 3 - Admin, Governance, And Report Query Boundaries

## Summary

Admin audit, admin user, admin review/report, governance workbench, and skill
report SQL now live behind explicit repository modules. Existing service module
imports remain available as facade modules so API routes and tests keep the
same public import paths.

## Changes

- Added `server-python/app/admin/audit_repository.py`.
- Added `server-python/app/admin/user_repository.py`.
- Added `server-python/app/admin/review_report_repository.py`.
- Added `server-python/app/governance/workbench_repository.py`.
- Added `server-python/app/reports/report_repository.py`.
- Converted the old modules into compatibility facades:
  - `server-python/app/admin/audit_logs.py`
  - `server-python/app/admin/users.py`
  - `server-python/app/admin/review_reports.py`
  - `server-python/app/governance/workbench.py`
  - `server-python/app/reports/skill_reports.py`
- Extended `server-python/tests/test_post_cutover_architecture.py` so these
  facade modules cannot regain direct `sqlalchemy.text` usage.

## SQL Inventory Delta

Before this milestone:

- `repository-query`: 54 `text()` calls.
- `service-domain`: 345 `text()` calls.

After this milestone:

- `repository-query`: 105 `text()` calls.
- `service-domain`: 294 `text()` calls.

Moved into repository-query modules:

| File | `text()` calls |
| --- | ---: |
| `app/admin/review_report_repository.py` | 16 |
| `app/governance/workbench_repository.py` | 16 |
| `app/admin/user_repository.py` | 11 |
| `app/reports/report_repository.py` | 6 |
| `app/admin/audit_repository.py` | 2 |

The remaining route-level SQL is unchanged and limited to:

- `app/api/labels.py`
- `app/api/device_auth.py`

## Verification

Commands run from `server-python`.

```powershell
uv run pytest tests/test_admin_audit_logs.py tests/test_admin_user_management.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py tests/test_governance_workbench.py tests/test_skill_report_submit.py -q
uv run pytest tests/test_post_cutover_architecture.py -q
uv run python scripts/sql_inventory.py
uv run pytest tests -q
```

Results:

- Target admin/governance/report tests: `30 passed, 1 warning`.
- Architecture guardrail tests: `6 passed`.
- SQL inventory: passed, with `repository-query` increased to 105 calls.
- Full Python backend suite: `715 passed, 1 warning`.

## Follow-Up

Milestone 4 should focus on mutation transaction boundaries for lifecycle,
review, promotion, and publish flows. This milestone intentionally preserved
existing function names and import paths so public API behavior stayed stable.
