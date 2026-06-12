# Skill Read Repository Boundary Result

Date: 2026-06-12

Milestone: 2 - Skill Read Surface Repository Boundary

## Summary

`server-python/app/api/skills.py` no longer owns direct `sqlalchemy.text` calls.
The skill read, file/download, tag, and ClawHub compatibility bridge helpers now
live under `server-python/app/skills/`.

This milestone preserves public API behavior and keeps `app.api.skills` exports
available for existing tests and dependent modules while moving SQL out of the
route module.

## Changes

- Added `server-python/app/skills/read_repository.py` as the extracted bridge
  repository for existing skill read/search/detail/version/file/tag/download and
  compatibility helpers.
- Added explicit domain import boundaries:
  - `server-python/app/skills/file_repository.py`
  - `server-python/app/skills/tag_repository.py`
  - `server-python/app/skills/compat_repository.py`
- Reduced `server-python/app/api/skills.py` to route glue, reader/writer
  injection support, redirects, request binding, response wrapping, and
  delegation.
- Updated tests that monkeypatch file-content helpers to target the repository
  module after the import boundary move.
- Updated the post-cutover architecture allowlist so `app/api/skills.py` is no
  longer permitted to call `sqlalchemy.text` directly.

## SQL Inventory Delta

Before this milestone:

- `api-route`: 69 `text()` calls.
- `app/api/skills.py`: 54 `text()` calls.

After this milestone:

- `api-route`: 15 `text()` calls.
- `repository-query`: 54 `text()` calls.
- `app/skills/read_repository.py`: 54 `text()` calls.
- `app/api/skills.py`: 0 direct `text()` calls.

The remaining route-level SQL is limited to:

- `app/api/labels.py`
- `app/api/device_auth.py`

## Verification

Commands run from `server-python` unless noted.

```powershell
uv run pytest tests/test_skill_search.py tests/test_skill_detail.py tests/test_skill_versions.py tests/test_skill_version_detail.py tests/test_skill_file_metadata.py tests/test_skill_file_content.py tests/test_skill_download.py tests/test_skill_tags.py tests/test_clawhub_search.py tests/test_clawhub_skill_detail.py tests/test_clawhub_skills_list.py tests/test_clawhub_resolve.py -q
uv run pytest tests/test_post_cutover_architecture.py -q
uv run python scripts/sql_inventory.py
uv run pytest tests -q
cd ..\web; corepack pnpm run test:e2e:smoke
```

Results:

- Target skill/compat tests: `93 passed, 1 warning`.
- Architecture guardrail tests: `5 passed`.
- SQL inventory: passed, with `api-route` reduced to 15 calls.
- Full Python backend suite: `714 passed, 1 warning`.
- Web smoke E2E: `6 passed`.

## Follow-Up

Milestone 3 should apply the same pattern to admin, governance, and report query
modules. Milestone 5 may later move selected mutation-heavy helpers from
explicit SQL to ORM, but this milestone intentionally kept read/projection SQL
explicit and isolated.
