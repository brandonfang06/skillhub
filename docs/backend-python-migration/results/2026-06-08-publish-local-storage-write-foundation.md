# Publish Local Storage Write Foundation Result

Date: 2026-06-08

## Summary

Completed the Python local storage write foundation for publish/upload without migrating any
publish route and without writing database rows.

Python now has helpers for:

- Java-compatible file object keys: `skills/{skillId}/{versionId}/{path}`;
- Java-compatible bundle object key: `packages/{skillId}/{versionId}/bundle.zip`;
- local object writes under a configured storage base path;
- per-file SHA-256 metadata;
- future `skill_file` row metadata;
- bundle zip creation preserving package entry order and bytes;
- file count, total size, `bundleReady`, and `downloadReady` stats;
- path safety checks that reject non-normalized package entry paths.

## Route Ownership

No route ownership moved to Python in this milestone.

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills` | java | java |
| POST | `/api/v1/publish` | java | java |
| POST | `/api/v1/skills/{namespace}/publish` | java | java |
| POST | `/api/web/skills/{namespace}/publish` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish/validate` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish` | java | java |

## Files Changed

- `server-python/app/publish/storage.py`
- `server-python/tests/test_publish_storage.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-publish-local-storage-write-foundation.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Verification

Focused checks completed during implementation:

- `cd server-python; uv run pytest tests/test_publish_storage.py -q`
  - `6 passed`
- `cd server-python; uv run pytest tests/test_publish_storage.py tests/test_hybrid_makefile.py -q`
  - `12 passed`

Final checks completed:

- `cd server-python; uv run pytest`
  - `203 passed, 1 warning`
- `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `18 passed`
- `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - passed
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-storage-foundation-smoke`
  - storage tests: `6 passed`
  - publish ownership: all Java/Vite status comparisons matched
  - Playwright smoke: `6 passed`
  - `.dev/publish-storage-foundation-contract-result.json` written
- Port cleanup check after live gate:
  - no `LISTENING` entries on `3000`, `8080`, or `8081`; only `TIME_WAIT` entries remained.

- `git diff --check`
  - passed; Windows line-ending warnings only.
- `git diff --name-only -- server`
  - printed nothing.

## Risks

- Storage helpers write local files but are not yet wrapped in a DB transaction.
- If later DB inserts fail after file writes, compensation behavior still needs a dedicated design.
- Scanner, review task creation, audit logs, events, and replacement cleanup remain deferred.
- No publish HTTP route uses this helper yet.

## Follow-Up

Next milestone should plan and implement DB transaction foundation tests:

- create or reuse `skill`;
- create `skill_version`;
- insert `skill_file` rows from `SkillFileWriteRecord`;
- update version stats;
- keep scanner/review/audit/event deferred unless explicitly planned.
