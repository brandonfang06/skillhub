# Post-Cutover Architecture Inventory Result

Date: 2026-06-12

Milestone: 1 - Post-Cutover Architecture Inventory And Guardrails

## Summary

The Python backend now has a post-cutover maintenance track separate from the
Java-to-Python migration documents. This milestone adds SQL inventory tooling and
static guardrails so future maintainability work does not spread route-level SQL
or introduce ORM models before the selective ORM milestone.

## SQL Inventory

`server-python/scripts/sql_inventory.py` reports `sqlalchemy.text` usage by file
and category:

- `api-route`
- `repository-query`
- `service-domain`
- `migration-bootstrap`
- `test`

Current route-level SQL bridge allowlist:

- `app/api/device_auth.py`
- `app/api/labels.py`
- `app/api/skills.py`

These files remain allowlisted only as migration bridge code. Later milestones
will reduce this list by moving SQL into repository/query modules.

Initial inventory output summary:

| Category | `text()` calls |
| --- | ---: |
| `api-route` | 69 |
| `migration-bootstrap` | 11 |
| `service-domain` | 345 |

Top SQL files from the initial inventory:

| File | Category | `text()` calls |
| --- | --- | ---: |
| `app/api/skills.py` | `api-route` | 54 |
| `app/auth/account_merge.py` | `service-domain` | 24 |
| `app/lifecycle/skill.py` | `service-domain` | 23 |
| `app/lifecycle/hard_delete.py` | `service-domain` | 21 |
| `app/review/approval.py` | `service-domain` | 20 |
| `app/promotion/workflow.py` | `service-domain` | 19 |
| `app/admin/review_reports.py` | `service-domain` | 16 |
| `app/governance/workbench.py` | `service-domain` | 16 |
| `app/api/labels.py` | `api-route` | 14 |

## Large File Inventory

Largest application modules from the initial scan:

- `server-python/app/api/skills.py` - about 3355 lines.
- `server-python/app/lifecycle/skill.py` - about 912 lines.
- `server-python/app/review/query.py` - about 847 lines.
- `server-python/app/admin/review_reports.py` - about 727 lines.
- `server-python/app/promotion/workflow.py` - about 718 lines.
- `server-python/app/review/approval.py` - about 709 lines.

## Guardrails Added

- `server-python/tests/test_post_cutover_architecture.py` fails if a new
  `server-python/app/api/*.py` module starts using `sqlalchemy.text` without an
  explicit allowlist reason.
- The same test suite fails if SQLAlchemy declarative ORM constructs appear
  before the selective ORM milestone.
- `server-python/AGENTS.md` now documents post-cutover SQL and ORM rules.

## Verification

Completed verification for this milestone:

```powershell
cd server-python
uv run python scripts/sql_inventory.py
uv run pytest tests/test_post_cutover_architecture.py -q
uv run pytest tests -q
```

Results:

- `uv run python scripts/sql_inventory.py`: passed and produced the inventory summarized above.
- `uv run pytest tests/test_post_cutover_architecture.py -q`: `5 passed`.
- `uv run pytest tests -q`: `714 passed, 1 warning`.
