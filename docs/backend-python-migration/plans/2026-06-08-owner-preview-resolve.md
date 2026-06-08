# Owner Preview Resolve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated parity coverage for portal skill resolve routes and explicitly preserve
Java's published-only resolve behavior for owner-preview versions.

**Architecture:** Portal resolve already belongs to Python. This milestone passes the local
`X-Mock-User-Id` context through the route and repository boundary, but keeps version resolution
published-only because Java `SkillQueryService.resolveVersion(...)` calls `assertPublishedVersion`
for exact versions, tags, and latest resolution. Java remains the read-only contract runtime.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080` for live contract comparison, Playwright smoke for frontend
sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/web/skills/{namespace}/{slug}/resolve`

Behavior in scope:

- Forward normalized `X-Mock-User-Id` into the portal resolve reader.
- Keep anonymous published resolve unchanged.
- Keep owner / namespace `ADMIN` exact pending-version resolve rejected, matching Java.
- Compare Java, Python, and Vite proxy aliases for published and pending selectors.

Behavior intentionally out of scope:

- Do not allow non-published owner-preview resolve targets. Java does not allow this today.
- Do not migrate file bytes, bundle downloads, storage streaming, download counters, or redirects.
- Do not broaden skill lookup for private, hidden, inactive, or archived skills.
- Do not change ClawHub `/api/v1/resolve` routes in this milestone.
- Do not migrate publish, review, promotion, lifecycle, OAuth, token, or session mutations.
- Do not modify `server/`.

## Route Ownership

No Vite route ownership changes are expected. These routes are already Python-owned:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | python | Add authenticated context forwarding and live negative preview parity. |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_resolve.py`.
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
  - portal resolve forwards normalized `X-Mock-User-Id` to injected reader;
  - missing or blank header forwards `None`;
  - ClawHub resolve routes keep their existing reader signature.
- [ ] Update `resolve_skill_version(...)` to read `X-Mock-User-Id` and pass `current_user_id`.
- [ ] Re-run route tests.

### Task 2. Repository Signature

- [ ] Update `read_skill_resolve(...)` to accept optional `current_user_id`.
- [ ] Keep published-only SQL filtering unchanged for this milestone.
- [ ] Re-run focused Python tests.

### Task 3. Live Verification Gate

- [ ] Add `verify-owner-preview-resolve-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic fixtures:
  - public team skill owned by `local-user`;
  - published `1.0.0` with file metadata for fingerprint;
  - pending `1.1.0` with file metadata for negative selector checks;
  - namespace `ADMIN` membership for `local-admin`.
- [ ] Compare stable Java/Python/Vite contracts for:
  - anonymous published exact version resolve;
  - owner published exact version resolve;
  - namespace admin published exact version resolve;
  - owner pending exact version status;
  - namespace admin pending exact version status.
- [ ] Ignore volatile `timestamp` and `requestId`.
- [ ] Run Playwright smoke.
- [ ] Update `server-python/tests/test_hybrid_makefile.py`.

### Task 4. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/route-registry.md`.
- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update `docs/backend-python-migration/windows-live-verification.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-owner-preview-resolve.md`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-resolve-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Published portal resolve remains unchanged for anonymous, owner, and namespace admin callers.
- Owner and namespace admin pending-version resolve remains rejected with Java-compatible status.
- Vite `/api/v1` and `/api/web` aliases both route to Python for portal resolve.
- ClawHub resolve routes are unchanged.
- No `server/` file is modified.
