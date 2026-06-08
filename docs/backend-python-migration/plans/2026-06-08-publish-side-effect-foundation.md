# Publish Side-Effect Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Python helpers for Java-compatible publish side-effect decisions and DB writes
without taking ownership of any publish HTTP route.

**Architecture:** Keep publish side effects as narrow helper functions under `server-python/app/publish/`.
The helpers consume IDs/statuses returned by the DB transaction foundation and produce/write review,
scanner, event, and audit side effects that a later publish route can orchestrate. No route handler
or Vite ownership changes are made in this milestone.

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

## Java Reference

Read-only references:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityScanService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewTask.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityAudit.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/resources/db/migration/V1__init_schema.sql`
- `server/skillhub-app/src/main/resources/db/migration/V3__phase3_review_social_tables.sql`
- `server/skillhub-app/src/main/resources/db/migration/V23__review_and_idempotency_timestamptz.sql`
- `server/skillhub-app/src/main/resources/db/migration/V35__security_audit.sql`

Java-compatible behavior to mirror:

- `PENDING_REVIEW` publish creates a `review_task` with status `PENDING` and emits a
  `ReviewSubmittedEvent` intent.
- `PUBLISHED` auto-publish emits a `SkillPublishedEvent` intent.
- `PRIVATE` / `UPLOADED` publish creates no review task and no published event.
- When scanner is enabled, Java creates a `security_audit` row with `SUSPICIOUS`, `is_safe=false`,
  `findings_count=0`, and `findings=[]`.
- When scanner is enabled, Java publishes a scan task. Upload mode uses bundle key
  `packages/{skillId}/{versionId}/bundle.zip`; local mode uses a temp skill path.
- When scanner is enabled and version is not already `PUBLISHED`, Java transitions the version to
  `SCANNING`.
- ClawHub publish app service writes `audit_log` action `COMPAT_PUBLISH` with target type
  `SKILL_VERSION`.

## Files

Create:

- `server-python/app/publish/side_effects.py`
- `server-python/tests/test_publish_side_effects.py`
- `docs/backend-python-migration/results/2026-06-08-publish-side-effect-foundation.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Tasks

### Task 1: Side-Effect Intent Tests

- [ ] Write failing tests in `server-python/tests/test_publish_side_effects.py` for:
  - `PENDING_REVIEW` creates review and review-submitted intent.
  - `PUBLISHED` creates published intent and no review task.
  - `UPLOADED` creates neither review nor published intent.
  - scanner enabled creates security audit and scan task.
  - scanner enabled moves non-published statuses to `SCANNING`.
  - scanner enabled keeps `PUBLISHED` status unchanged.
  - ClawHub compat audit payload uses `COMPAT_PUBLISH`.

- [ ] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
uv run pytest tests/test_publish_side_effects.py -q
```

Expected before implementation: fail with `ModuleNotFoundError: No module named 'app.publish.side_effects'`.

### Task 2: Implement Side-Effect Helper

- [ ] Create `server-python/app/publish/side_effects.py`.
- [ ] Implement dataclasses:
  - `PublishSideEffectInput`
  - `PublishSideEffectPlan`
  - `PublishSideEffectResult`
  - `ScanTaskPayload`
  - `PublishEventIntent`
- [ ] Implement:
  - `plan_publish_side_effects(...)`
  - `build_scan_task_payload(...)`
  - `build_compat_publish_audit_detail(...)`
  - `apply_publish_side_effects(connection, request)`

SQL stays inside this helper. No route handler changes.

### Task 3: Windows Gate

- [ ] Add `verify-publish-side-effects-foundation-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] Gate behavior:
  - run `uv run pytest tests/test_publish_side_effects.py -q`;
  - start hybrid stack;
  - verify publish POST routes still match Java status through Vite;
  - write `.dev/publish-side-effects-foundation-contract-result.json`;
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-side-effects-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Not In This Milestone

- No publish POST route ownership.
- No Python HTTP endpoint for publish.
- No actual scanner HTTP call.
- No Redis stream integration.
- No notification delivery.
- No replacement cleanup or storage compensation.
- No CSRF/session bridge changes.
