# Read Files Helper Split

Date: 2026-06-18

## Scope

Split the first low-risk helper group out of
`server-python/app/skills/read_repository.py` without changing SQL query behavior,
route contracts, or public import paths.

## Changes

- Added `server-python/app/skills/read_files.py` for file and download helpers.
- Kept `read_repository.py` importing and re-exporting the moved helpers so
  existing `app.api.skills` and `app.skills.read_repository` imports continue to
  work.
- Left repository SQL functions in place for this milestone.
- Added a boundary test proving the new helper module owns the moved helpers and
  the legacy import paths still point at the same objects.

## Verification Focus

This slice intentionally covers the recently found session-sensitive download
workflow:

- file content helpers
- skill download helpers
- publish-review-download session flow
- legacy import compatibility

## Follow-Up

Future splits should continue to avoid SQL behavior changes in the same commit.
The next low-risk candidates are access helpers and response formatter helpers,
with targeted import-boundary tests before moving any query functions.
