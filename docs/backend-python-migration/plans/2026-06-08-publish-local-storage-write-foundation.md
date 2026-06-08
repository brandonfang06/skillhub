# Publish Local Storage Write Foundation Plan

Date: 2026-06-08

## Summary

This milestone builds the Python local object-storage write foundation for publish/upload. It does
not migrate any publish HTTP route and does not write database rows.

The goal is to mirror the deterministic storage part of Java `SkillPublishService`:

- file object key: `skills/{skillId}/{versionId}/{entry.path}`;
- bundle object key: `packages/{skillId}/{versionId}/bundle.zip`;
- SHA-256 per file;
- file metadata fields needed for future `skill_file` rows;
- bundle zip containing package entries.

## Route Ownership

No route ownership changes.

These routes stay Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

## Java Reference

Read-only Java reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`

Storage behavior to mirror:

- For each `PackageEntry`, write bytes to `skills/{skillId}/{versionId}/{entry.path}`.
- Compute lowercase hex SHA-256 from exact entry bytes.
- Prepare file metadata:
  - `versionId`
  - `filePath`
  - `fileSize`
  - `contentType`
  - `sha256`
  - `storageKey`
- Build bundle zip with each entry's `entry.path` and exact bytes.
- Write bundle to `packages/{skillId}/{versionId}/bundle.zip`.
- Return `fileCount`, `totalSize`, `bundleReady=true`, `downloadReady=fileCount > 0`.

## Allowed Files

Create:

- `server-python/app/publish/storage.py`
- `server-python/tests/test_publish_storage.py`
- `docs/backend-python-migration/results/2026-06-08-publish-local-storage-write-foundation.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

Forbidden:

- No `server/` changes.
- No new publish route.
- No Vite publish ownership change.
- No DB writes.
- No scanner trigger.
- No review task, audit log, or event creation.

## Implementation Shape

Add `server-python/app/publish/storage.py`:

- `SkillFileWriteRecord`
- `StoredPackageResult`
- `skill_storage_key(skill_id, version_id, path)`
- `bundle_storage_key(skill_id, version_id)`
- `build_bundle_zip(entries)`
- `write_local_package_objects(storage_base_path, skill_id, version_id, entries)`

Safety requirements:

- Resolve paths under `storage_base_path`.
- Reject any object key that escapes the storage base.
- Create parent directories as needed.
- Preserve exact file bytes.
- Preserve package entry order in the bundle zip, matching Java's `buildBundle(...)`.

## Tests First

Add `server-python/tests/test_publish_storage.py` before implementation.

Tests:

- key helpers return Java-compatible keys.
- `write_local_package_objects(...)` writes each entry to the expected path.
- returned file metadata includes exact `version_id`, path, size, content type, sha256, storage key.
- `total_size`, `file_count`, `bundle_ready`, and `download_ready` are correct.
- bundle zip exists at Java-compatible bundle key.
- bundle zip contains entry names and bytes in package entry order.
- path traversal in an object key is rejected before writing outside storage base.
- empty package writes an empty bundle and returns `download_ready=false`.

## Windows Live Gate

Add `verify-publish-storage-foundation-smoke` to `scripts/dev-hybrid.ps1`.

The gate must:

- run `uv run pytest tests/test_publish_storage.py -q`;
- start hybrid stack;
- verify publish POST Java ownership through Vite for:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/global/publish`
  - `POST /api/web/skills/global/publish`
- run Playwright smoke;
- write `.dev/publish-storage-foundation-contract-result.json`.

No Python publish HTTP route is called because no route exists yet.

## Verification

Run before commit:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
.\node_modules\.bin\tsc.CMD --noEmit
```

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-storage-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Follow-Up

Next milestone should add DB transaction planning and tests:

- insert or reuse `skill`;
- insert `skill_version`;
- insert `skill_file` rows using `SkillFileWriteRecord`;
- update version stats;
- keep scanner/review/audit/event deferred until an explicit milestone.
