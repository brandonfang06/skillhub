# Read Resolve And Compare Helper Split

Date: 2026-06-18

## Scope

Moved resolve and compare pure helpers out of
`server-python/app/skills/read_repository.py` without changing SQL query
behavior, route contracts, or public import paths.

## Changes

- Added `server-python/app/skills/read_resolve.py` for version resolution
  helper logic and resolve response building.
- Added `server-python/app/skills/read_compare.py` for version compare constants,
  file diff helpers, hunk generation, and compare response building.
- Kept `read_repository.py` re-exporting moved names for legacy imports.
- Added boundary tests proving `read_resolve.py` and `read_compare.py` own the
  moved helpers while `app.api.skills` and `read_repository.py` keep the same
  objects.

## Verification

- `uv run pytest tests/test_skill_read_resolve_boundary.py tests/test_skill_resolve_repository.py tests/test_skill_read_compare_boundary.py tests/test_skill_version_compare.py -q`
- `uv run pytest tests -q` -> `800 passed, 1 warning`
- `uv run python -m compileall app/skills/read_resolve.py app/skills/read_compare.py app/skills/read_repository.py -q` -> passed
- `git diff --check` -> passed

## Follow-Up

Stop the helper-only cleanup here unless a specific maintenance issue appears.
Further splitting of SQL-backed read functions should be planned separately with
query ownership, transaction, and endpoint regression coverage.
