# Authenticated Skill Detail Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Python-owned public skill detail routes so authenticated local mock users receive
Java-compatible viewer capability flags.

**Architecture:** Keep the existing public visibility boundary intact and add only viewer-context
calculation for already visible public skill details. Python reads `X-Mock-User-Id`, namespace
membership, and promotion-request state from PostgreSQL; Java remains the read-only contract
reference.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080` for live comparison, Playwright smoke for frontend sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`

Behavior in scope:

- Preserve anonymous/public detail contract.
- If `X-Mock-User-Id` maps to the skill owner, set:
  - `canManageLifecycle: true`
  - `canReport: false`
- If `X-Mock-User-Id` maps to a namespace member with role `OWNER` or `ADMIN`, set:
  - `canManageLifecycle: true`
- For non-global namespaces, set `canSubmitPromotion: true` only when:
  - namespace status is `ACTIVE`;
  - namespace type is not `GLOBAL`;
  - skill status is `ACTIVE`;
  - a published version exists;
  - no `promotion_request` exists for the source skill with status `PENDING` or `APPROVED`;
  - viewer can manage the skill by owner or namespace role.

Behavior intentionally out of scope:

- Do not expose private, hidden, archived, draft, pending review, or rejected owner-preview records.
- Do not migrate lifecycle, promotion, review, publish, or storage mutations.
- Do not treat `SUPER_ADMIN` as portal skill-detail manager; Java currently does not grant this
  capability in portal detail.
- Do not change `/api/v1/auth/me`.
- Do not modify `server/`.

## Route Ownership

No new route ownership changes. These routes are already Python-owned:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}` | python | Add viewer capability flags only. |
| GET | `/api/web/skills/{namespace}/{slug}` | python | Same contract as v1 alias. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_detail.py`.
- Modify `server-python/tests/test_skill_detail_repository.py`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Write result file after verification.
- Update `docs/backend-python-migration/windows-live-verification.md` if a new live gate is added.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not change Vite proxy ownership unless live comparison proves it is required.

## TDD Tasks

### Task 1. Detail Response Capability Builder

- [ ] Add failing tests in `server-python/tests/test_skill_detail_repository.py`:
  - owner gets `canManageLifecycle: true`, `canReport: false`;
  - namespace `ADMIN` or `OWNER` gets `canManageLifecycle: true`;
  - non-global active namespace with published version and no promotion block gets
    `canSubmitPromotion: true`;
  - global namespace never gets `canSubmitPromotion`.
- [ ] Run `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_detail_repository.py -q`
  and confirm the new tests fail because the builder still returns anonymous flags.
- [ ] Update `build_skill_detail_response(...)` to accept optional viewer context fields from the
  row and compute the flags.
- [ ] Re-run the repository tests and confirm they pass.

### Task 2. Route Viewer Context

- [ ] Add failing tests in `server-python/tests/test_skill_detail.py`:
  - `X-Mock-User-Id` is forwarded to the injected `skill_detail_reader`;
  - missing header forwards `None`;
  - blank header forwards `None`.
- [ ] Run `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_detail.py -q`
  and confirm the new tests fail because the route currently forwards only namespace/slug.
- [ ] Update `get_skill_detail(...)` to read `X-Mock-User-Id` and pass normalized viewer id to the
  reader.
- [ ] Re-run route tests and confirm they pass.

### Task 3. Database Reader Capability Context

- [ ] Add failing tests or extend existing repository tests so row inputs cover:
  - `namespace_type`;
  - `namespace_role`;
  - `promotion_blocked`.
- [ ] Update `read_skill_detail(...)`:
  - add `n.type AS namespace_type`;
  - if viewer id is present, read `namespace_member.role` for the skill namespace;
  - read whether a `promotion_request` with status `PENDING` or `APPROVED` exists;
  - populate `current_user_id`, `namespace_role`, and `promotion_blocked` before calling the builder.
- [ ] Keep public visibility checks unchanged.
- [ ] Run all Python tests.

### Task 4. Live Verification Gate

- [ ] Add `verify-auth-detail-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic fixtures for:
  - public global skill owned by `local-user`;
  - public team skill owned by `local-user`;
  - `local-admin` as namespace `ADMIN` or `OWNER` for the team namespace;
  - optional `promotion_request` blocker case if practical.
- [ ] Compare stable Java/Python/Vite contracts for:
  - anonymous request;
  - owner request via `X-Mock-User-Id: local-user`;
  - namespace admin request via `X-Mock-User-Id: local-admin`.
- [ ] Ignore volatile `timestamp` and `requestId`.
- [ ] Run Playwright smoke.
- [ ] Update `server-python/tests/test_hybrid_makefile.py`.

### Task 5. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-authenticated-skill-detail-capabilities.md`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; node_modules\.bin\tsc.CMD --noEmit`
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-auth-detail-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Anonymous public skill detail remains unchanged.
- Owner and namespace manager capability flags match Java for public visible skills.
- Global namespace promotion remains disabled.
- Team namespace promotion is enabled only for eligible manager/owner public skills without pending
  or approved promotion requests.
- Owner preview and non-public visibility remain deferred.
- No `server/` file is modified.
