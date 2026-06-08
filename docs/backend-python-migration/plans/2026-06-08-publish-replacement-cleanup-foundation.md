# Publish Replacement Cleanup Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Python helpers for Java-compatible replacement cleanup and storage-delete
compensation without taking ownership of any publish HTTP route.

**Architecture:** Keep replacement cleanup in a focused Python module under
`server-python/app/publish/`. DB cleanup and local object cleanup remain separate helpers so a
future publish route can run DB deletion in transaction and storage deletion after commit. No route
handler or Vite ownership changes are made in this milestone.

**Tech Stack:** FastAPI Python backend, pytest, SQLAlchemy `text`, local filesystem object storage,
uv, Windows hybrid verification.

---

## Boundary

No route ownership changes.

Still Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

Do not modify any file under `server/`.

## Java Reference

Read-only references:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityScanService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillStorageDeletionCompensationService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/SkillStorageDeletionCompensation.java`
- `server/skillhub-app/src/main/resources/db/migration/V33__skill_delete_storage_compensation.sql`

Java-compatible behavior to mirror:

- A replacement attempt must reject an existing `PUBLISHED` version.
- If the replaced version is the skill's `latest_version_id`, clear `skill.latest_version_id`
  before deleting the version.
- Delete any pending review task for the replaced version.
- Collect existing `skill_file.storage_key` values and append bundle key
  `packages/{skillId}/{versionId}/bundle.zip`.
- Delete `skill_file` rows for the replaced version.
- Soft-delete active `security_audit` rows by setting `deleted_at`.
- Delete the replaced `skill_version` row.
- Storage object deletion happens after DB commit in Java. Python helper only returns keys and
  provides local deletion/compensation helpers.
- If storage deletion fails, record `skill_storage_delete_compensation` with status `PENDING`,
  attempt count `0`, and serialized storage keys.

## Files

Create:

- `server-python/app/publish/replacement.py`
- `server-python/tests/test_publish_replacement.py`
- `docs/backend-python-migration/results/2026-06-08-publish-replacement-cleanup-foundation.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Tasks

### Task 1: Replacement Cleanup Tests

- [ ] Write failing tests in `server-python/tests/test_publish_replacement.py` for:
  - published existing version is rejected.
  - latest-version FK is cleared before version delete.
  - pending review task is deleted.
  - file rows are deleted.
  - security audits are soft-deleted.
  - storage keys include file keys plus bundle key.
  - local object delete removes files under storage base.
  - local object delete rejects path escape.
  - failed local delete records compensation row.

- [ ] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
uv run pytest tests/test_publish_replacement.py -q
```

Expected before implementation: fail with `ModuleNotFoundError: No module named 'app.publish.replacement'`.

### Task 2: Implement Replacement Helper

- [ ] Create `server-python/app/publish/replacement.py`.
- [ ] Implement dataclasses:
  - `ReplaceableVersion`
  - `ReplacementCleanupResult`
  - `StorageDeleteCompensationInput`
- [ ] Implement:
  - `bundle_storage_key(...)`
  - `cleanup_replaceable_version(connection, version)`
  - `delete_local_storage_objects(storage_base_path, storage_keys)`
  - `record_storage_delete_compensation(connection, request)`
  - `delete_local_storage_objects_or_record_compensation(...)`

SQL stays inside this helper. No route handler changes.

### Task 3: Windows Gate

- [ ] Add `verify-publish-replacement-foundation-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] Gate behavior:
  - run `uv run pytest tests/test_publish_replacement.py -q`;
  - start hybrid stack;
  - verify publish POST routes still match Java status through Vite;
  - write `.dev/publish-replacement-foundation-contract-result.json`;
  - run Playwright smoke;
  - stop hybrid stack.
- [ ] Extend `server-python/tests/test_hybrid_makefile.py` static guard.

### Task 4: Docs And Verification

- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update `docs/backend-python-migration/windows-live-verification.md`.
- [ ] Write result document.
- [ ] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-replacement-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Not In This Milestone

- No publish POST route ownership.
- No Python HTTP endpoint for publish.
- No live DB mutation through Python route.
- No object storage deletion after commit hook.
- No MinIO/S3 delete implementation.
- No replacement cleanup integration into `create_publish_db_records(...)`.
