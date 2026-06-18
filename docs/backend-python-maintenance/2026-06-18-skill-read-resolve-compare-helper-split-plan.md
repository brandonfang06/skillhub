# Skill Read Resolve And Compare Helper Split Plan

Date: 2026-06-18

## Goal

Finish the low-risk `read_repository.py` helper cleanup by moving resolve and
compare pure helpers into focused modules without changing SQL behavior, route
contracts, or legacy import paths.

## Scope

Create `server-python/app/skills/read_resolve.py` for:

- `has_text`
- `compute_version_fingerprint`
- `find_latest_version`
- `matched_value`
- `resolve_version_row`
- `build_resolve_response`

Create `server-python/app/skills/read_compare.py` for:

- `COMPARE_MAX_FILE_BYTES`
- `COMPARE_MAX_LINES`
- `BINARY_FILE_EXTENSIONS`
- `is_binary_compare_path`
- `split_compare_lines`
- `build_compare_hunks`
- `build_compare_file`
- `build_compare_response`

Keep every SQL-backed `read_*` function in `read_repository.py`.

## Steps

1. Add boundary tests proving `read_resolve.py` and `read_compare.py` own the
   moved helpers while `read_repository.py` and `app.api.skills` still expose
   the same objects.
2. Run the new tests first and confirm they fail because the new modules do not
   exist yet.
3. Move resolve helpers into `read_resolve.py`; update `read_repository.py` to
   import and re-export them.
4. Move compare helpers into `read_compare.py`; update `read_repository.py` to
   import and re-export them.
5. Run targeted tests:

```powershell
cd server-python
uv run pytest tests/test_skill_read_resolve_boundary.py tests/test_skill_resolve_repository.py tests/test_skill_read_compare_boundary.py tests/test_skill_version_compare.py -q
```

6. Run full verification:

```powershell
cd server-python
uv run pytest tests -q
cd ..
git diff --check
```

## Risk Controls

- Do not edit SQL strings.
- New helper modules must not import `read_repository.py`.
- Keep legacy import identity through `read_repository.py` and `app.api.skills`.
- Stop after this helper split; do not split SQL query functions in this
  milestone.

