# Read Pure Helper Split

Date: 2026-06-18

## Scope

Moved pure access, portal response, and ClawHub/CLI compatibility helpers out of
`server-python/app/skills/read_repository.py` without changing SQL query
behavior, route contracts, storage behavior, or public import paths.

## Changes

- Added `server-python/app/skills/read_access.py`.
- Added `server-python/app/skills/read_responses.py`.
- Added `server-python/app/skills/read_compat.py`.
- Kept `read_repository.py` re-exporting moved names for legacy imports.
- Updated compatibility facade modules to import helper ownership modules
  directly while leaving SQL-backed functions in `read_repository.py`.
- Added boundary tests for access, response, and compatibility helper ownership.

## Verification

- `uv run pytest tests/test_skill_read_access_boundary.py tests/test_skill_versions_repository.py tests/test_skill_version_detail.py tests/test_skill_detail_repository.py tests/test_clawhub_star.py -q`
- `uv run pytest tests/test_skill_read_responses_boundary.py tests/test_skill_versions_repository.py tests/test_skill_version_detail_repository.py tests/test_skill_detail_repository.py tests/test_skill_search_repository.py tests/test_skill_tags.py tests/test_skill_download.py -q`
- `uv run pytest tests/test_skill_read_compat_boundary.py tests/test_clawhub_search_repository.py tests/test_clawhub_skills_list_repository.py tests/test_clawhub_resolve_repository.py tests/test_clawhub_skill_detail_repository.py tests/test_cli_skills.py tests/test_clawhub_star.py -q`
- `uv run pytest tests -q` -> `798 passed, 1 warning`
- `git diff --check` -> passed

## Follow-Up

The next low-risk split is compare/resolve pure helpers. SQL-backed read
functions should stay in `read_repository.py` until a separate repository
boundary plan covers query ownership and transaction tests.
