# Publish DB Transaction Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish DB transaction foundation. This milestone adds the helper needed by a
future publish route to create or reuse the skill container, create the version row, create file
metadata rows, and update version statistics.

No publish HTTP route ownership changed. Java remains the owner for all publish POST routes.

## Route Ownership

| Route | Owner Before | Owner After | Notes |
| --- | --- | --- | --- |
| `POST /api/v1/skills` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/v1/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/v1/skills/{namespace}/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/web/skills/{namespace}/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/cli/v1/skills/{namespace}/publish/validate` | Java | Java | No proxy ownership change. |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java | Java | No proxy ownership change. |

## Implemented

- Added `server-python/app/publish/transaction.py`.
- Added Java-compatible initial status selection:
  - `PUBLISHED` for auto-publish;
  - `UPLOADED` for private visibility;
  - `PENDING_REVIEW` otherwise.
- Added parsed metadata JSON and manifest JSON builders.
- Added `create_publish_db_records(...)` helper with one transaction boundary.
- Reuses an existing `(namespace_id, slug, owner_id)` skill when present.
- Rejects an existing archived skill before inserting a new version.
- Creates `skill`, `skill_version`, and `skill_file` records.
- Updates `skill_version.file_count`, `total_size`, `bundle_ready`, and `download_ready`.
- Updates `skill.latest_version_id` only for `PUBLISHED` or `UPLOADED`.
- Added `verify-publish-db-foundation-smoke` to the Windows hybrid verification script.

## Explicitly Not Implemented

- No Python publish HTTP route.
- No Vite publish POST ownership change.
- No live Python DB mutation through HTTP.
- No scanner trigger.
- No review task creation.
- No audit log or event creation.
- No replacement cleanup or storage compensation.
- No CSRF/session bridge changes.

## Verification

Focused checks:

```text
cd server-python
uv run pytest tests/test_publish_transaction.py tests/test_hybrid_makefile.py -q
13 passed in 0.30s
```

Final verification:

```text
cd server-python
uv run pytest
210 passed, 1 warning in 3.39s
```

```text
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
1 passed, 18 tests passed
```

```text
cd web
.\node_modules\.bin\tsc.CMD --noEmit
exit 0
```

```text
scripts\dev-hybrid.ps1 verify-publish-db-foundation-smoke
7 passed
allProxyMatchesJava: true
6 passed
```

```text
netstat -ano | Select-String ':3000\s|:8080\s|:8081\s'
Only TIME_WAIT entries; no LISTENING ports remained.
```

```text
git diff --check
Only CRLF conversion warnings; no whitespace errors.
```

```text
git diff --name-only -- server
No output.
```

## Risks

- The transaction helper currently uses fake-engine tests rather than a live DB mutation test. This
  is intentional because no Python publish route owns DB writes yet.
- Scanner, review, audit/event, and compensation behavior remain separate foundations or route
  milestone work.
- The next route milestone must re-check SQL against a real database before enabling publish POST
  ownership.

## Follow-Up

The next milestone should choose between:

- migrate an internal/private publish route using the accumulated package, dry-run, storage, and DB
  foundations; or
- add scanner/review/audit foundations first, then move publish route ownership as a complete
  vertical slice.
