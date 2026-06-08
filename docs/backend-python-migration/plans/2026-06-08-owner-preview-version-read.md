# Owner Preview Version Read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Python-owned skill version list and version detail routes so lifecycle managers
can read owner-preview non-published versions with Java-compatible access rules.

**Architecture:** Keep Java under `server/` as a read-only contract reference and keep Python route
ownership unchanged. Python will read `X-Mock-User-Id`, resolve the viewer's namespace role, and
apply Java's `canManageRestrictedSkill` rule to decide whether non-published versions are visible.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080` for live contract comparison, Playwright smoke for frontend
sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/versions`
- `GET /api/web/skills/{namespace}/{slug}/versions`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`

Behavior in scope:

- Anonymous and non-manager callers continue to see only `PUBLISHED` versions.
- Skill owners and namespace `OWNER` / `ADMIN` callers can see lifecycle-manager versions:
  - `PUBLISHED`
  - `PENDING_REVIEW`
  - `UPLOADED`
  - `DRAFT`
  - `REJECTED`
  - `YANKED`
  - `SCANNING`
  - `SCAN_FAILED`
- Manager version list sorting matches Java:
  - status priority: `PUBLISHED`, `REJECTED`, `PENDING_REVIEW`, `UPLOADED`, `DRAFT`, `SCANNING`,
    `SCAN_FAILED`, `YANKED`;
  - `published_at` descending with nulls last;
  - `created_at` descending with nulls last;
  - `id` descending.
- Manager version detail can read non-published versions.
- Non-manager version detail for non-published versions returns the same not-published error shape
  as Java/Python currently use for not-found version access.

Behavior intentionally out of scope:

- Do not broaden skill lookup for private, hidden, inactive, or archived skills.
- Do not migrate owner-preview file metadata in this milestone.
- Do not migrate file bytes, bundle downloads, storage reads, or download counters.
- Do not migrate publish, review, promotion, lifecycle, OAuth, token, or session mutations.
- Do not modify `server/`.

## Route Ownership

No Vite route ownership changes are expected. These routes are already Python-owned:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions` | python | Add manager-visible lifecycle versions. |
| GET | `/api/web/skills/{namespace}/{slug}/versions` | python | Same contract as v1 alias. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | python | Add manager-visible non-published detail. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_versions.py`.
- Modify `server-python/tests/test_skill_versions_repository.py`.
- Modify `server-python/tests/test_skill_version_detail.py`.
- Modify `server-python/tests/test_skill_version_detail_repository.py`.
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

### Task 1. Route Viewer Context

- [ ] Add failing route tests:
  - versions list forwards normalized `X-Mock-User-Id` to the injected reader;
  - version detail forwards normalized `X-Mock-User-Id` to the injected reader;
  - missing or blank header forwards `None`.
- [ ] Update route reader signatures to include `current_user_id`.
- [ ] Re-run route tests.

### Task 2. Version List Manager Access

- [ ] Add failing repository tests for `build_versions_page_response(...)` or reader behavior:
  - manager-visible lifecycle statuses are ordered by Java lifecycle priority;
  - non-manager remains published-only.
- [ ] Update `read_skill_versions(...)`:
  - resolve skill with existing public visibility boundary;
  - read namespace role when `current_user_id` is present;
  - if viewer can manage, include Java lifecycle-manager statuses;
  - otherwise include only `PUBLISHED`;
  - apply Java-compatible ordering and pagination.
- [ ] Re-run focused tests.

### Task 3. Version Detail Manager Access

- [ ] Add failing repository tests:
  - owner can read `PENDING_REVIEW` version detail;
  - namespace `ADMIN` can read `REJECTED` version detail;
  - non-manager cannot read non-published version detail.
- [ ] Update `read_skill_version_detail(...)`:
  - accept `current_user_id`;
  - resolve namespace role;
  - allow non-published detail only when manager;
  - preserve current published behavior for anonymous callers.
- [ ] Re-run focused tests.

### Task 4. Live Verification Gate

- [ ] Add `verify-owner-preview-version-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic fixtures:
  - public team skill owned by `local-user`;
  - published `1.0.0`;
  - rejected `1.2.0`;
  - pending review `1.1.0`;
  - namespace `ADMIN` membership for `local-admin`.
- [ ] Compare stable Java/Python/Vite contracts for:
  - anonymous version list;
  - owner version list;
  - namespace admin version list;
  - owner pending version detail;
  - anonymous pending version detail error behavior.
- [ ] Ignore volatile `timestamp` and `requestId`.
- [ ] Run Playwright smoke.
- [ ] Update `server-python/tests/test_hybrid_makefile.py`.

### Task 5. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/route-registry.md`.
- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update `docs/backend-python-migration/windows-live-verification.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-owner-preview-version-read.md`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-version-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Anonymous version list and published version detail remain unchanged.
- Owner and namespace manager version list matches Java for lifecycle-manager-visible statuses and
  ordering.
- Owner and namespace manager version detail can read non-published versions that Java allows.
- Non-manager version detail for non-published versions remains rejected.
- No `server/` file is modified.
