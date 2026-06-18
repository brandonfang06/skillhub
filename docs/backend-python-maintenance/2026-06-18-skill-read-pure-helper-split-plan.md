# Skill Read Pure Helper Split Plan

Date: 2026-06-18

## Goal

Continue shrinking `server-python/app/skills/read_repository.py` by moving pure
access, response, and compatibility helpers into focused modules without
changing SQL behavior, route contracts, storage behavior, or public import
paths.

## Current Context

The first helper split moved file and download helpers into
`server-python/app/skills/read_files.py`. `read_repository.py` still contains a
mix of pure helper code and SQL-backed repository functions. This milestone
keeps the next split low-risk by moving only pure helpers and leaving every SQL
query function in place.

## Target Modules

Create `server-python/app/skills/read_access.py` for lifecycle and access
policy helpers:

- `LIFECYCLE_MANAGER_STATUSES`
- `LIFECYCLE_LIST_PRIORITY`
- `lifecycle_visible_statuses`
- `lifecycle_list_priority`
- `can_manage_lifecycle_for_row`
- `can_access_skill_row`
- `assert_skill_row_access`

Create `server-python/app/skills/read_responses.py` for portal response
builders and Java-compatible formatting helpers:

- `to_java_instant`
- `to_epoch_millis`
- `normalize_page_request`
- `paginate_rows`
- `build_versions_page_response`
- `build_version_detail_response`
- `build_tag_response`
- `to_lifecycle_version`
- `build_skill_detail_response`
- `build_skill_summary_response`
- `build_skill_search_response`

Create `server-python/app/skills/read_compat.py` for ClawHub and CLI
compatibility helpers:

- `to_clawhub_canonical_slug`
- `from_clawhub_canonical_slug`
- `build_clawhub_search_response`
- `build_cli_search_response`
- `build_clawhub_skills_list_response`
- `build_clawhub_resolve_response`
- `build_cli_resolve_response`
- `build_clawhub_skill_detail_response`
- `clawhub_resolve_selectors`

Keep these in `read_repository.py` for later milestones:

- `read_namespace_role`, because it executes SQL.
- search parsing helpers: `normalize_search_sort`, `parse_non_negative_int`,
  `parse_positive_int`, `normalize_label_slugs`, `normalize_search_keyword`,
  `build_skill_search_ts_query`.
- resolve and compare helpers: `compute_version_fingerprint`,
  `find_latest_version`, `matched_value`, `resolve_version_row`,
  `build_resolve_response`, `is_binary_compare_path`, `split_compare_lines`,
  `build_compare_hunks`, `build_compare_file`, `build_compare_response`.
- all `read_*`, `create_*`, `delete_*`, and `increment_*` SQL-backed functions.

## Files To Change

- Create `server-python/app/skills/read_access.py`.
- Create `server-python/app/skills/read_responses.py`.
- Create `server-python/app/skills/read_compat.py`.
- Modify `server-python/app/skills/read_repository.py` to import and re-export
  moved names while removing duplicate definitions.
- Modify `server-python/app/skills/tag_repository.py` so `build_tag_response`
  comes from `read_responses.py`; keep tag SQL functions in `read_repository.py`.
- Modify `server-python/app/skills/compat_repository.py` so compatibility
  formatters come from `read_compat.py`; keep SQL-backed read functions in
  `read_repository.py`.
- Create `server-python/tests/test_skill_read_access_boundary.py`.
- Create `server-python/tests/test_skill_read_responses_boundary.py`.
- Create `server-python/tests/test_skill_read_compat_boundary.py`.
- Create `docs/backend-python-maintenance/results/2026-06-18-read-pure-helper-split.md`
  after implementation and verification.

## Implementation Steps

1. Add failing boundary tests.
   - `test_skill_read_access_boundary.py` imports `app.skills.read_access` and
     proves every moved access helper is the same object exposed by
     `app.skills.read_repository` and `app.api.skills`.
   - `test_skill_read_responses_boundary.py` imports
     `app.skills.read_responses` and proves every moved response helper is the
     same object exposed by `app.skills.read_repository` and `app.api.skills`.
   - `test_skill_read_compat_boundary.py` imports `app.skills.read_compat` and
     proves every moved compatibility helper is the same object exposed by
     `app.skills.read_repository`, `app.api.skills`, and
     `app.skills.compat_repository`.
   - Verify first failure with:

```powershell
cd server-python
uv run pytest tests/test_skill_read_access_boundary.py tests/test_skill_read_responses_boundary.py tests/test_skill_read_compat_boundary.py -q
```

Expected first result: failure for missing `read_access`, `read_responses`, and
`read_compat` modules.

2. Move access helpers.
   - Create `read_access.py`.
   - Import `SkillResolveError` from `app.skills.read_files`.
   - Import `is_namespace_manager` and `is_namespace_member` from
     `app.auth.policy`.
   - Move the exact existing access helper implementations.
   - Update `read_repository.py` imports and remove duplicate definitions.
   - Verify with:

```powershell
cd server-python
uv run pytest tests/test_skill_read_access_boundary.py tests/test_skill_versions_repository.py tests/test_skill_version_detail.py tests/test_skill_detail_repository.py tests/test_clawhub_star.py -q
```

3. Move portal response helpers.
   - Create `read_responses.py`.
   - Move the exact existing timestamp, pagination, version, tag, detail,
     summary, and search response helpers.
   - Import `can_manage_lifecycle_for_row` from `read_access.py`.
   - In `build_skill_detail_response`, replace the duplicated owner-or-manager
     expression with `can_manage_lifecycle_for_row(row, current_user_id,
     namespace_role)`.
   - Update `read_repository.py` imports and remove duplicate definitions.
   - Update `tag_repository.py` to import `build_tag_response` from
     `read_responses.py`.
   - Verify with:

```powershell
cd server-python
uv run pytest tests/test_skill_read_responses_boundary.py tests/test_skill_versions_repository.py tests/test_skill_version_detail_repository.py tests/test_skill_detail_repository.py tests/test_skill_search_repository.py tests/test_skill_tags.py tests/test_skill_download.py -q
```

4. Move ClawHub and CLI compatibility helpers.
   - Create `read_compat.py`.
   - Import `to_epoch_millis` from `read_responses.py`.
   - Move the exact existing canonical slug, ClawHub response, CLI response, and
     selector helpers.
   - Update `read_repository.py` imports and remove duplicate definitions.
   - Update `compat_repository.py` to import compatibility helpers from
     `read_compat.py`.
   - Verify with:

```powershell
cd server-python
uv run pytest tests/test_skill_read_compat_boundary.py tests/test_clawhub_search_repository.py tests/test_clawhub_skills_list_repository.py tests/test_clawhub_resolve_repository.py tests/test_clawhub_skill_detail_repository.py tests/test_cli_skills.py tests/test_clawhub_star.py -q
```

5. Document and verify the completed milestone.
   - Add result note under
     `docs/backend-python-maintenance/results/2026-06-18-read-pure-helper-split.md`.
   - Run the full backend regression:

```powershell
cd server-python
uv run pytest tests -q
cd ..
git diff --check
```

Expected final result: all backend tests pass and `git diff --check` exits `0`.

## Risk Controls

- Do not edit SQL strings in `read_repository.py`.
- Do not rename public helper functions.
- Do not change route imports in `server-python/app/api/skills.py`.
- Do not move `read_namespace_role` in this milestone.
- New helper modules must not import `read_repository.py`.
- If a failure appears outside the touched areas, first check for import cycles
  before changing behavior.
- Preserve legacy import identity through `read_repository.py` and
  `app.api.skills`.

## Completion Criteria

- New helper modules own the moved pure helper groups.
- Existing legacy import paths still expose the same helper objects.
- `read_repository.py` is smaller without SQL behavior changes.
- Targeted boundary and behavior tests pass.
- Full backend pytest suite passes.
- Result note records scope, verification, and follow-up.

