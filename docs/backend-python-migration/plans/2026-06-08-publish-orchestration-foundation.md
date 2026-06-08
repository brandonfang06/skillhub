# Publish Orchestration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the existing Python publish foundation helpers into a single service-level write
workflow without moving any publish HTTP route ownership.

**Architecture:** Add a narrow orchestration helper under `server-python/app/publish/` that accepts
already-resolved publish inputs, opens DB transactions, optionally cleans a replaceable
non-published version, allocates skill/version IDs, writes local storage objects, finalizes DB file
rows/stats, applies side effects, and deletes replacement storage after commit. This remains a
Python-internal helper; future milestones will add HTTP binding and live DB workflow tests only
after this helper is stable.

**Tech Stack:** FastAPI Python backend, SQLAlchemy async engine, explicit SQL bridge helpers,
pytest, uv, Windows hybrid verification.

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

The previous publish milestones built individual foundations: package validation, dry-run model,
storage writes, DB prepare/finalize, side effects, and replacement cleanup. Before a Python publish
route can safely own traffic, those helpers need one tested orchestration boundary with explicit
ordering and after-commit cleanup behavior.

## Files

Create:

- `server-python/app/publish/orchestration.py`
- `server-python/tests/test_publish_orchestration.py`
- `docs/backend-python-migration/results/2026-06-08-publish-orchestration-foundation.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Tasks

### Task 1: Orchestration Tests

- [x] Add failing tests to `server-python/tests/test_publish_orchestration.py` for:
  - `execute_publish_write(...)` prepares DB records, writes local storage, finalizes file rows,
    and applies publish side effects in one workflow.
  - replaceable non-published version cleanup runs before new version creation and old storage
    deletion runs after the DB transaction commits.
  - publish POST routes remain outside this helper.

- [x] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
uv run pytest tests/test_publish_orchestration.py -q
```

Expected before implementation: fail with missing `app.publish.orchestration`.

### Task 2: Implement Orchestration Helper

- [x] Add dataclasses:
  - `PublishWriteInput`
  - `PublishWriteResult`
- [x] Add function:
  - `execute_publish_write(engine, request)`
- [x] Sequence:
  1. start DB transaction;
  2. clean replaceable version when provided;
  3. prepare `skill` / `skill_version`;
  4. write local storage objects with returned IDs;
  5. finalize `skill_file` rows and version stats;
  6. apply publish side effects;
  7. commit transaction;
  8. delete old replacement storage after commit, recording compensation if deletion fails.
- [x] Keep focused orchestration tests green.

### Task 3: Windows Gate

- [x] Add `verify-publish-orchestration-foundation-smoke` to `scripts/dev-hybrid.ps1`.
- [x] Gate behavior:
  - run `uv run pytest tests/test_publish_orchestration.py -q`;
  - start hybrid stack;
  - verify publish POST routes still match Java status through Vite;
  - write `.dev/publish-orchestration-foundation-contract-result.json`;
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-orchestration-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Not In This Milestone

- No publish POST route ownership.
- No FastAPI publish endpoint.
- No multipart request parsing.
- No dry-run HTTP route.
- No scanner HTTP call or Redis stream delivery.
- No live DB mutation through a Python route.
