# Skill Detail Owner Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Python-owned public skill detail routes with Java-compatible owner preview
projection fields for lifecycle managers.

**Architecture:** Keep the current public detail visibility boundary unchanged and add only the
viewer-specific lifecycle projection used by Java `SkillLifecycleProjectionService`. Python reads
published version, newest newer non-published version, namespace manager role, and rejected review
comment from PostgreSQL; Java remains a read-only contract reference for live comparison.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080` for live contract comparison, Playwright smoke for frontend
sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`

Behavior in scope:

- Preserve anonymous public detail behavior.
- If the current viewer can manage the skill, expose `ownerPreviewVersion` when a non-published,
  non-yanked version is newer than the resolved published version.
- Manager means the same boundary already implemented in Python detail:
  - current user is the skill owner; or
  - current user has namespace role `OWNER` or `ADMIN`.
- Projection rules match Java:
  - `publishedVersion` is the resolved published version, if any.
  - `ownerPreviewVersion` is the newest newer non-published version only for managers.
  - `headlineVersion` is `publishedVersion` when published exists; otherwise it is
    `ownerPreviewVersion`.
  - `resolutionMode` is `PUBLISHED` when `headlineVersion` is published, `OWNER_PREVIEW` when only
    owner preview is surfaced, or `NONE` when no lifecycle version is visible.
  - `canInteract` is true only when `headlineVersion` is missing or published.
- If `ownerPreviewVersion.status == "REJECTED"`, expose the rejected review task
  `review_comment` as `ownerPreviewReviewComment`.

Behavior intentionally out of scope:

- Do not broaden detail visibility for private, hidden, archived, or non-public skills.
- Do not allow owner-preview access to version detail, file metadata, tag files, resolve, or
  download routes.
- Do not migrate publish, review, promotion, storage, or lifecycle mutations.
- Do not treat `SUPER_ADMIN` as a portal detail manager.
- Do not change Vite route ownership; the routes are already Python-owned.
- Do not modify `server/`.

## Route Ownership

No route ownership changes. These routes are already Python-owned:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}` | python | Add owner preview projection fields. |
| GET | `/api/web/skills/{namespace}/{slug}` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_detail.py`.
- Modify `server-python/tests/test_skill_detail_repository.py`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/windows-live-verification.md`.
- Write result file after verification.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not change Vite proxy ownership.

## TDD Tasks

### Task 1. Response Projection Builder

- [ ] Add failing tests in `server-python/tests/test_skill_detail_repository.py`:
  - manager with only pending preview gets `headlineVersion` as pending, `publishedVersion: null`,
    `ownerPreviewVersion` as pending, `resolutionMode: OWNER_PREVIEW`, and `canInteract: false`;
  - manager with published plus newer rejected preview keeps `headlineVersion` as published,
    exposes `ownerPreviewVersion`, keeps `resolutionMode: PUBLISHED`, and exposes
    `ownerPreviewReviewComment`;
  - anonymous/non-manager does not receive `ownerPreviewVersion`;
  - non-published versions older than the published version are ignored.
- [ ] Run `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_detail_repository.py -q`
  and confirm the new tests fail because owner preview is still hard-coded to `None`.
- [ ] Update `build_skill_detail_response(...)` to derive published, owner-preview, headline,
  resolution mode, and `canInteract` from row projection fields.
- [ ] Re-run the repository tests and confirm they pass.

### Task 2. Database Reader Projection Context

- [ ] Update `read_skill_detail(...)` to query the owner preview candidate only when the viewer can
  manage lifecycle.
- [ ] Use Java recency ordering for preview comparison:
  `created_at ASC NULLS LAST`, then `id ASC NULLS LAST`; a preview is newer than published when
  that tuple compares greater than the published tuple.
- [ ] Exclude `PUBLISHED` and `YANKED` from preview candidates.
- [ ] Query `review_task.review_comment` only for a rejected owner preview version.
- [ ] Keep current public visibility checks unchanged.
- [ ] Run focused repository and route tests.

### Task 3. Route-Level Regression

- [ ] Extend `server-python/tests/test_skill_detail.py` only if route fixtures need new projection
  fields.
- [ ] Confirm existing route tests still pass and `X-Mock-User-Id` forwarding remains unchanged.

### Task 4. Live Verification Gate

- [ ] Add `verify-owner-preview-detail-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic fixtures for:
  - public skill owned by `local-user` with published `1.0.0` and newer rejected `1.1.0`;
  - rejected `review_task.review_comment`;
  - namespace manager access via `local-admin` if practical with the existing fixture style.
- [ ] Compare stable Java/Python/Vite contracts for:
  - anonymous request, which must not expose owner preview;
  - owner request via `X-Mock-User-Id: local-user`, which must expose owner preview and review
    comment;
  - Vite `/api/v1` and `/api/web` proxy responses, which must match Python.
- [ ] Ignore volatile `timestamp` and `requestId`.
- [ ] Run Playwright smoke.
- [ ] Update `server-python/tests/test_hybrid_makefile.py`.

### Task 5. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/route-registry.md`.
- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update `docs/backend-python-migration/windows-live-verification.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-skill-detail-owner-preview.md`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-detail-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Anonymous public skill detail remains unchanged.
- Owner and namespace manager detail responses expose Java-compatible `ownerPreviewVersion` only
  for newer non-published, non-yanked versions.
- Rejected owner preview responses include Java-compatible `ownerPreviewReviewComment`.
- Published skills keep published headline/resolution even when a newer owner preview exists.
- Preview-only manager-visible details use `OWNER_PREVIEW` resolution and `canInteract: false`.
- No `server/` file is modified.
