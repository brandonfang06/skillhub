# Publish Transaction Split Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Python publish DB transaction helper into prepare/finalize phases so a future
publish route can create skill/version IDs before writing storage objects.

**Architecture:** Keep the existing `create_publish_db_records(...)` wrapper behavior for backward
compatibility, but implement it in terms of connection-level prepare/finalize helpers. A later
orchestration milestone will call prepare, write storage with the returned IDs, finalize file rows
and stats, apply side effects, and then delete replacement storage after commit.

**Tech Stack:** FastAPI Python backend, pytest, SQLAlchemy `text`, uv, Windows hybrid verification.

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

## Why This Milestone Exists

The previous DB transaction foundation accepted `StoredPackageResult`, but local storage keys need
`skill_id` and `version_id`. Java creates the `SkillVersion` before writing storage objects, then
persists `SkillFile` rows and stats afterward. Python needs the same shape before any publish route
can be safely enabled.

## Files

Create:

- `docs/backend-python-migration/results/2026-06-08-publish-transaction-split-foundation.md`

Modify:

- `server-python/app/publish/transaction.py`
- `server-python/tests/test_publish_transaction.py`
- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Tasks

### Task 1: Transaction Split Tests

- [x] Add failing tests to `server-python/tests/test_publish_transaction.py` for:
  - `prepare_publish_db_records(...)` creates/reuses skill and inserts `skill_version`, returning
    `skill_id`, `version_id`, status, and latest update decision without inserting `skill_file`.
  - `finalize_publish_db_records(...)` inserts file rows, updates stats, and updates skill metadata.
  - existing `create_publish_db_records(...)` still performs the same full sequence.

- [x] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
uv run pytest tests/test_publish_transaction.py -q
```

Expected before implementation: fail with missing `prepare_publish_db_records` /
`finalize_publish_db_records`.

### Task 2: Implement Split Helpers

- [x] Add dataclasses:
  - `PublishDbPrepareInput`
  - `PublishDbPrepareResult`
  - `PublishDbFinalizeInput`
- [x] Add functions:
  - `prepare_publish_db_records(connection, request)`
  - `finalize_publish_db_records(connection, request)`
- [x] Refactor `create_publish_db_records(engine, request)` to call prepare/finalize inside one
  `engine.begin()` block.
- [x] Keep all existing tests green.

### Task 3: Windows Gate

- [x] Add `verify-publish-transaction-split-smoke` to `scripts/dev-hybrid.ps1`.
- [x] Gate behavior:
  - run `uv run pytest tests/test_publish_transaction.py -q`;
  - start hybrid stack;
  - verify publish POST routes still match Java status through Vite;
  - write `.dev/publish-transaction-split-contract-result.json`;
  - run Playwright smoke;
  - stop hybrid stack.
- [x] Extend `server-python/tests/test_hybrid_makefile.py` static guard.

### Task 4: Docs And Verification

- [x] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [x] Update `docs/backend-python-migration/windows-live-verification.md`.
- [x] Write result document.
- [x] Run:

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-transaction-split-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Not In This Milestone

- No publish POST route ownership.
- No Python HTTP endpoint for publish.
- No storage write orchestration.
- No side-effect orchestration.
- No live DB mutation through Python route.
