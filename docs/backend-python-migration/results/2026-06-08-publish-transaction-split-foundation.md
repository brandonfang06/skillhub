# Publish Transaction Split Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish DB transaction split foundation. The DB helper now has explicit
prepare and finalize phases so future publish orchestration can allocate `skill_id` and
`version_id`, write storage objects with Java-compatible keys, then persist file rows and stats.

No publish POST route ownership changed in this milestone.

## Route Ownership

| Route | Before | After |
| --- | --- | --- |
| `POST /api/v1/skills` | Java | Java |
| `POST /api/v1/publish` | Java | Java |
| `POST /api/v1/skills/{namespace}/publish` | Java | Java |
| `POST /api/web/skills/{namespace}/publish` | Java | Java |
| `POST /api/cli/v1/skills/{namespace}/publish/validate` | Java | Java |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java | Java |

## Implemented

- Added `PublishDbPrepareInput`, `PublishDbPrepareResult`, and `PublishDbFinalizeInput`.
- Added `prepare_publish_db_records(...)` for skill lookup/create and `skill_version` insert.
- Added `finalize_publish_db_records(...)` for `skill_file` rows, version stats, readiness flags,
  and skill metadata/latest-version update.
- Refactored `create_publish_db_records(...)` to preserve the existing one-call behavior while
  using prepare/finalize internally.
- Added `verify-publish-transaction-split-smoke` to the Windows hybrid live gate.

## Not Implemented

- No Python publish HTTP route.
- No route ownership movement.
- No live DB mutation through a Python route.
- No storage write orchestration.
- No scanner trigger orchestration.
- No publish side-effect orchestration.
- No replacement cleanup orchestration.

## Verification

Focused checks:

```text
uv run pytest tests/test_publish_transaction.py -q
9 passed in 0.27s
```

```text
uv run pytest tests/test_publish_transaction.py tests/test_hybrid_makefile.py -q
15 passed in 0.32s
```

Final milestone gate:

```text
uv run pytest
229 passed, 1 warning in 3.65s
```

```text
vitest vite.config.test.ts --run
18 passed
```

```text
tsc --noEmit
exit 0
```

```text
scripts\dev-hybrid.ps1 verify-publish-transaction-split-smoke
9 passed
allProxyMatchesJava: true
6 passed
```

Post-gate port cleanup check:

```text
netstat showed only TIME_WAIT entries on 3000/8080/8081, with no LISTENING processes.
```

## Risks And Follow-Up

- The split helper still uses explicit SQL bridge code to preserve Java contract parity; ORM
  refactoring remains a post-migration Group H topic.
- Future publish orchestration must ensure storage writes happen after prepare and that finalize,
  side effects, and replacement cleanup are sequenced with explicit compensation behavior.
- The next publish milestone should integrate the prepare/storage/finalize/side-effect helper
  sequence behind tests before moving any POST route ownership.
