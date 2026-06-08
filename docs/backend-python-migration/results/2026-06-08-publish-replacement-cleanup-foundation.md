# Publish Replacement Cleanup Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish replacement cleanup foundation. This milestone adds helpers for the
Java publish behavior that removes a replaceable non-published version before creating a new version
with the same semantic version.

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

- Added `server-python/app/publish/replacement.py`.
- Added Java-compatible replacement cleanup behavior:
  - rejects replacement of existing `PUBLISHED` versions;
  - clears `skill.latest_version_id` when it points at the replaced version;
  - deletes pending `review_task`;
  - collects `skill_file.storage_key` values and appends bundle key;
  - deletes `skill_file` rows;
  - soft-deletes active `security_audit` rows;
  - deletes the replaced `skill_version` row.
- Added local storage cleanup helper with storage-base path escape protection.
- Added `skill_storage_delete_compensation` insert helper for failed local deletion.
- Added `verify-publish-replacement-foundation-smoke` to the Windows hybrid verification script.

## Explicitly Not Implemented

- No Python publish HTTP route.
- No Vite publish POST ownership change.
- No live Python DB mutation through HTTP.
- No MinIO/S3 object delete implementation.
- No after-commit hook orchestration.
- No integration into `create_publish_db_records(...)`.
- No scanner, review, or notification route orchestration.

## Verification

Focused checks:

```text
cd server-python
uv run pytest tests/test_publish_replacement.py tests/test_hybrid_makefile.py -q
13 passed in 0.36s
```

Final verification:

```text
cd server-python
uv run pytest
227 passed, 1 warning in 3.66s
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
scripts\dev-hybrid.ps1 verify-publish-replacement-foundation-smoke
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

- Replacement cleanup is fake-connection tested in this milestone. A real DB workflow gate should
  be added before enabling publish route ownership.
- Local object deletion is implemented; MinIO/S3 deletion remains future work.
- Java runs storage deletion after DB commit. Python only exposes separable helpers in this
  milestone; orchestration remains route/workflow work.

## Follow-Up

The next milestone can start the first Python-owned internal publish route only if it wires the
existing package, dry-run, storage, DB transaction, side-effect, and replacement helpers into one
verified workflow. Otherwise, add a dedicated real DB publish workflow gate first.
