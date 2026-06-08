# Owner Preview File Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Python-owned skill version file metadata routes so lifecycle managers can read
file metadata for owner-preview non-published versions.

**Architecture:** Reuse the owner/namespace-manager access helpers introduced for version detail.
Python keeps the public skill visibility boundary unchanged, allows non-published version file
metadata only for lifecycle managers, and continues to treat Java as the read-only contract
reference during live verification.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080` for live contract comparison, Playwright smoke for frontend
sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`

Behavior in scope:

- Anonymous and non-manager callers continue to read only `PUBLISHED` version file metadata.
- Skill owners and namespace `OWNER` / `ADMIN` callers can read file metadata for lifecycle-manager
  non-published versions such as `PENDING_REVIEW` and `REJECTED`.
- Non-manager requests for non-published version file metadata return the same rejected status as
  Java.
- Returned metadata contract remains:
  - `id`
  - `filePath`
  - `fileSize`
  - `contentType`
  - `sha256`

Behavior intentionally out of scope:

- Do not migrate tag file preview access. Tag file routes remain published-version only.
- Do not migrate file bytes, bundle downloads, storage streaming, download counters, or redirects.
- Do not broaden skill lookup for private, hidden, inactive, or archived skills.
- Do not migrate publish, review, promotion, lifecycle, OAuth, token, or session mutations.
- Do not modify `server/`.

## Route Ownership

No Vite route ownership changes are expected. These routes are already Python-owned:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/files` | python | Add manager-visible non-published version file metadata. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/files` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_file_metadata.py`.
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
  - version file metadata forwards normalized `X-Mock-User-Id` to injected reader;
  - missing or blank header forwards `None`;
  - tag file routes keep their existing reader signature.
- [ ] Update `list_skill_version_files(...)` to read `X-Mock-User-Id` and pass
  `current_user_id`.
- [ ] Re-run route tests.

### Task 2. Database Reader Access

- [ ] Update `read_skill_version_files(...)`:
  - accept `current_user_id`;
  - resolve public skill with existing visibility boundary;
  - read namespace role when `current_user_id` is present;
  - allow non-published version files only when `can_manage_lifecycle_for_row(...)` is true;
  - preserve published-only behavior for anonymous/non-manager callers;
  - preserve `ORDER BY file_path ASC`.
- [ ] Re-run focused Python tests.

### Task 3. Live Verification Gate

- [ ] Add `verify-owner-preview-files-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic fixtures:
  - public team skill owned by `local-user`;
  - published `1.0.0` with file metadata and matching local storage object;
  - pending `1.1.0` with file metadata and matching local storage object;
  - namespace `ADMIN` membership for `local-admin`.
- [ ] Compare stable Java/Python/Vite contracts for:
  - anonymous published version files;
  - owner pending version files;
  - namespace admin pending version files;
  - anonymous pending version files status.
- [ ] Ignore volatile `timestamp` and `requestId`.
- [ ] Run Playwright smoke.
- [ ] Update `server-python/tests/test_hybrid_makefile.py`.

### Task 4. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/route-registry.md`.
- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update `docs/backend-python-migration/windows-live-verification.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-owner-preview-file-metadata.md`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-files-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Anonymous published version file metadata remains unchanged.
- Owner and namespace manager can read non-published version file metadata that Java allows.
- Anonymous/non-manager non-published file metadata remains rejected.
- Tag file routes remain published-only and unchanged.
- No `server/` file is modified.
