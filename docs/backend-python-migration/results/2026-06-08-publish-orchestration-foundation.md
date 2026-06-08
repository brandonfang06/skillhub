# Publish Orchestration Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish orchestration foundation. The new service-level helper composes the
previous publish foundations into one testable write workflow while keeping all publish POST routes
Java-owned.

No publish route ownership changed in this milestone.

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

- Added `server-python/app/publish/orchestration.py`.
- Added `PublishWriteInput` and `PublishWriteResult`.
- Added `execute_publish_write(...)` to:
  - clean replaceable non-published versions inside the DB transaction;
  - allocate `skill_id` and `version_id`;
  - write local package objects with Java-compatible keys;
  - finalize file rows, stats, and skill metadata;
  - apply publish side effects;
  - delete old replacement storage after commit with compensation support.
- Added `verify-publish-orchestration-foundation-smoke` to the Windows hybrid live gate.

## Not Implemented

- No Python publish HTTP route.
- No route ownership movement.
- No multipart request parsing.
- No dry-run HTTP endpoint.
- No scanner HTTP call or Redis stream delivery.
- No CSRF/session publish behavior.
- No live DB mutation through a Python route.

## Verification

Focused checks:

```text
uv run pytest tests/test_publish_orchestration.py -q
3 passed in 0.32s
```

```text
uv run pytest tests/test_publish_orchestration.py tests/test_hybrid_makefile.py -q
8 passed in 0.39s
```

Final milestone gate:

```text
uv run pytest
231 passed, 1 warning in 3.53s
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
scripts\dev-hybrid.ps1 verify-publish-orchestration-foundation-smoke
3 passed
allProxyMatchesJava: true
6 passed
```

Post-review verification:

```text
uv run pytest tests/test_publish_replacement.py tests/test_publish_orchestration.py -q
10 passed in 0.32s
```

Post-gate port cleanup check:

```text
netstat showed only TIME_WAIT entries on 3000/8080/8081, with no LISTENING processes.
```

## Risks And Follow-Up

- Storage writes happen before DB commit, so future HTTP route work must preserve compensation
  behavior for failures after object writes.
- Scanner delivery is still represented as side-effect intent/payload only; actual scanner/Redis
  delivery remains a separate milestone.
- The next publish milestone should introduce a non-owned FastAPI handler or integration test
  boundary only if route ownership remains explicitly Java until the live mutation workflow is
  proven.
