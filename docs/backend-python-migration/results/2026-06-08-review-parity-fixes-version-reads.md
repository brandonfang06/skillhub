# Review Parity Fixes For Version Reads

Date: 2026-06-08

## Summary

Addressed reviewer feedback for Python-owned skill version/file read paths:

- version compare
- tag file metadata
- version file content
- tag file content on the same file-content migration surface

## Changes

- Removed hardcoded `s.visibility = 'PUBLIC'` from protected read-path skill lookups.
- Added a Python dynamic visibility check matching Java `VisibilityChecker` for `PUBLIC`,
  `NAMESPACE_ONLY`, and `PRIVATE` skills after resolving namespace role context.
- Kept existing hidden/archived route boundaries unchanged for this review-fix slice.
- Kept tag selector version resolution published-only to preserve Java parity.
- Changed version compare storage reads to load content only for added, removed, or modified files
  after comparing `file_path` and `sha256` metadata.

## Reviewer Feedback Triage

Must fix now:

- Version compare should not read unchanged file contents.
- Version compare, tag files, and version file content should not hardcode public-only visibility
  when Java performs dynamic visibility checks.

Handled in same migration surface:

- Tag file content had the same hardcoded public visibility lookup as version file content, so it
  was fixed with the same dynamic access rule while preserving published-only tag version behavior.

Deferred:

- S3/MinIO streaming parity remains part of the existing storage/download follow-up.
- Hidden/archived broader manager visibility remains outside this narrow review-fix slice.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_version_compare.py tests/test_skill_file_metadata.py tests/test_skill_file_content.py -q
```

Result: `30 passed, 1 warning`.

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest -q
```

Result: `273 passed, 1 warning`.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_version_compare.py`
- `server-python/tests/test_skill_file_metadata.py`
- `server-python/tests/test_skill_file_content.py`

No files under `server/` were modified.
