# Download Read Path Result

Date: 2026-06-08

## Summary

Migrated the planned v1 download read path to Python.

Python now owns ClawHub download redirect routes and portal v1 download stream routes. Java remains
the read-only contract reference, and `/api/web/.../download` aliases remain Java-owned/unmigrated.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/download/{canonicalSlug}` | java | python |
| GET | `/api/v1/download` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/download` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/download` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/download` | java | python |

Java-owned after this milestone:

- `GET /api/web/skills/{namespace}/{slug}/download`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download`
- publish/upload/delete/undelete/review download/auth/OAuth/token/session routes

## Implementation Notes

- Added Python `DownloadResult` helpers for raw stream responses.
- Added ClawHub redirect routes returning Java-compatible `302` `Location` values.
- Added portal v1 latest/version/tag download routes.
- Local bundle path follows Java: `packages/{skillId}/{versionId}/bundle.zip`.
- Missing bundle falls back to a zip built from `skill_file.storage_key` rows sorted by
  `file_path`.
- Published downloads increment:
  - `skill.download_count`;
  - `skill_version_stats.download_count`.
- Counter updates use SQLAlchemy async engine with explicit SQL as planned.
- `PUBLISHED`, `UPLOADED`, and `PENDING_REVIEW` download access matches Java behavior for public
  skills. Counters increment only for `PUBLISHED`.
- Fallback zip live comparison validates zip entry names and entry bytes rather than raw zip bytes,
  because Java and Python can produce different valid zip container byte streams.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_download.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`
- `docs/backend-python-migration/results/2026-06-08-download-read-path.md`

## Verification

Passed:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_download.py -q
19 passed
```

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_download.py tests/test_hybrid_makefile.py -q
25 passed
```

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'; uv run pytest
158 passed
```

```text
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
1 file passed, 17 tests passed
```

```text
cd web
.\node_modules\.bin\tsc.CMD --noEmit
passed
```

```text
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-download-smoke
```

Live gate passed:

- `allRedirectsJavaMatchPython: true`
- `allRedirectsPythonMatchProxy: true`
- `allRedirectLocationsExpected: true`
- `allContentJavaMatchesPython: true`
- `allContentPythonMatchesProxy: true`
- `allStatusesMatch: true`
- `countersMatchExpected: true`
- Playwright smoke: `6 passed`

Also verified no active listeners remained on `8080`, `8081`, or `3000`; only `TIME_WAIT`
connections were present after cleanup.

## Known Risks

- Python currently implements local filesystem stream behavior only. MinIO/S3 presigned redirect
  behavior remains out of scope.
- Web download aliases intentionally remain Java-owned/unmigrated.
- Download rate limiting remains Java-owned/out of scope.
- The live gate discovered Java allows public skill downloads for `UPLOADED` and `PENDING_REVIEW`.
  Python now matches this behavior for contract parity, even though the Java source comment says
  only owners should download those statuses.

## Follow-Up

- Revisit MinIO/S3 presigned URL behavior before production object storage migration.
- Revisit download authorization when Group C auth/session design becomes the active owner for
  real organization users.
- Do not start publish/upload migration until Group B storage-read assumptions and Group C auth
  assumptions are both accepted.
