# Owner Preview Version Compare Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate portal skill version compare routes to Python with Java-compatible owner-preview
access.

**Architecture:** Add Python portal compare routes for `/versions/compare`, using the same
public-skill and lifecycle-manager boundary already used by version detail and version file
metadata. The compare reader loads available file metadata and local storage content through the
configured Java-compatible local storage base path, then returns Java-shaped summary, files, hunks,
and lines. Java remains the read-only live contract reference.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Python `difflib` for
text hunks, local storage files under `.dev/java-storage` for Windows contract fixtures, Vite proxy
on port `3000`, Java Spring Boot on port `8080`, Playwright smoke for frontend sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/versions/compare`
- `GET /api/web/skills/{namespace}/{slug}/versions/compare`

Behavior in scope:

- Anonymous callers can compare published versions.
- Skill owners and namespace `OWNER` / `ADMIN` callers can compare Java-allowed owner-preview
  non-published versions.
- Non-manager callers are rejected when either side is non-published.
- Same-version compare is rejected.
- Text file diffs return Java-shaped hunks and ADD/DELETE lines.
- Added, removed, modified, binary, and truncated metadata shape is preserved.

Behavior intentionally out of scope:

- Do not migrate file bytes/download endpoints.
- Do not change ClawHub compatibility routes.
- Do not broaden skill lookup for private, hidden, inactive, or archived skills.
- Do not migrate publish, review, promotion, lifecycle, OAuth, token, or session mutations.
- Do not modify `server/`.

## Route Ownership

Vite proxy must add these Python-owned routes:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/compare` | python | Owner-preview version compare. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/compare` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Create `server-python/tests/test_skill_version_compare.py`.
- Modify `web/vite.config.ts`.
- Modify `web/vite.config.test.ts`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/windows-live-verification.md`.
- Write result file after verification.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.

## TDD Tasks

### Task 1. Route Contract

- [ ] Add failing route tests for:
  - `/api/v1/.../versions/compare` envelope response;
  - `/api/web/.../versions/compare` alias;
  - normalized `X-Mock-User-Id` forwarded to injected reader;
  - blank `X-Mock-User-Id` forwarded as `None`.
- [ ] Add Python route handler and injected reader call.
- [ ] Re-run focused tests.

### Task 2. Compare Builder

- [ ] Add failing unit tests for:
  - modified text file with ADD/DELETE lines;
  - added file;
  - removed file;
  - identical files omitted.
- [ ] Implement minimal compare builder with Java-shaped summary, file, hunk, and line objects.
- [ ] Re-run focused tests.

### Task 3. DB Reader And Storage

- [ ] Add DB reader tests where practical through helper functions.
- [ ] Implement `read_skill_version_compare(...)`:
  - public active skill lookup;
  - lifecycle-manager access using existing helpers;
  - version lookup without published filter;
  - published-only rejection for non-managers;
  - file metadata lookup ordered by path;
  - local storage content read by `storage_key`.
- [ ] Re-run Python tests.

### Task 4. Proxy And Live Gate

- [ ] Add Vite proxy ownership for both compare aliases.
- [ ] Update Vite proxy tests.
- [ ] Add `verify-owner-preview-compare-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic DB rows and local storage objects:
  - published `1.0.0`;
  - pending `1.1.0`;
  - one modified text file and one added text file.
- [ ] Compare Java/Python/Vite contracts for:
  - owner published-to-pending compare;
  - namespace admin published-to-pending compare;
  - anonymous published-to-pending status;
  - same-version status.
- [ ] Run Playwright smoke.

### Task 5. Docs, Verification, Commit

- [ ] Update route registry, sequence plan, Windows guide, and result doc.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-compare-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Java/Python/Vite compare contract matches for owner and namespace admin preview compare.
- Anonymous preview compare remains rejected.
- Same-version compare remains rejected.
- No `server/` file is modified.
