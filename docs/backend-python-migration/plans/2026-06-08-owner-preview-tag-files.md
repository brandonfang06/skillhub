# Owner Preview Tag Files Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Java-compatible tag file metadata behavior in Python while adding authenticated
context forwarding and live contract coverage.

**Architecture:** Keep tag file metadata routes published-only, matching Java's
`resolveVersionEntity(... tagName ...)` behavior. Python forwards normalized caller context for
route parity, but the DB reader intentionally rejects non-published tag targets. Java remains the
read-only live contract reference.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, Vite proxy on port
`3000`, Java Spring Boot on port `8080`, PowerShell live gate on Windows, Playwright smoke for
frontend sanity.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files`

Behavior in scope:

- Published tag file metadata remains readable through Python.
- `X-Mock-User-Id` is normalized and forwarded to injected Python route readers.
- Blank `X-Mock-User-Id` is forwarded as `None`.
- Non-published tag targets remain rejected for anonymous, skill owner, and namespace admin
  callers, because Java does not call `assertPreviewAccessible(...)` for tag selectors.
- Live Java/Python/Vite contract comparison covers published and pending tag targets.

Behavior intentionally out of scope:

- Do not enable owner-preview access for tag file metadata.
- Do not migrate tag file content, tag downloads, publish, review, OAuth, token, or session
  mutations.
- Do not modify `server/`.

## Java Reference Finding

Java `SkillQueryService.listFilesByTag(...)` accepts `currentUserId` and `userNsRoles`, but after
public skill access checks it calls:

```java
SkillVersion skillVersion = resolveVersionEntity(skill, null, tagName, null);
```

The tag path resolves through published-only version validation, not `assertPreviewAccessible(...)`.
Therefore Python must keep pending/rejected/draft tag targets rejected even for owners and namespace
admins.

## Route Ownership

Vite proxy ownership is already Python for these routes:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Published-only tag file metadata with authenticated context forwarding. |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Frontend alias with the same contract. |

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Modify `server-python/tests/test_skill_file_metadata.py`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/windows-live-verification.md`.
- Write `docs/backend-python-migration/results/2026-06-08-owner-preview-tag-files.md`.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.

## TDD Tasks

### Task 1. Route Header Forwarding

- [ ] Add failing tests in `server-python/tests/test_skill_file_metadata.py`:
  - tag route forwards `(namespace, slug, tagName, current_user_id)` to injected reader;
  - blank `X-Mock-User-Id` forwards `None`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_file_metadata.py -q`
- [ ] Expected before implementation: reader signature mismatch or missing forwarded user.
- [ ] Update `server-python/app/api/skills.py` minimally:
  - add `Header(default=None, alias="X-Mock-User-Id")`;
  - call `normalized_current_user_id(...)`;
  - pass current user to injected and DB readers.
- [ ] Re-run focused tests and expect pass.

### Task 2. DB Reader Signature

- [ ] Update `read_skill_tag_files(...)` to accept `current_user_id: str | None = None`.
- [ ] Keep the published-only SQL filter unchanged:
  - `WHERE id = :version_id AND status = 'PUBLISHED'`
- [ ] Re-run focused tests.

### Task 3. Windows Live Contract Gate

- [ ] Add `verify-owner-preview-tag-files-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] Add deterministic fixture rows:
  - active public team skill owned by `local-user`;
  - namespace admin/member role for `local-admin`;
  - published `1.0.0` tagged `stable`;
  - pending `1.1.0` tagged `preview`;
  - file metadata and matching local storage files.
- [ ] Compare Java, Python, Vite `/api/v1`, and Vite `/api/web` for:
  - anonymous published tag files;
  - owner published tag files;
  - namespace admin published tag files;
  - anonymous pending tag files status;
  - owner pending tag files status;
  - namespace admin pending tag files status.
- [ ] Write `.dev/owner-preview-tag-files-contract-result.json`.
- [ ] Run Playwright smoke inside the gate.

### Task 4. Docs And Verification

- [ ] Update route registry and migration sequence plan with the published-only tag parity note.
- [ ] Update Windows live verification docs with the new gate command.
- [ ] Write the result doc after verification.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - `$env:UV_CACHE_DIR='server-python\.uv-cache'; $env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config'); $env:DOCKER_HOST='tcp://127.0.0.1:2375'; powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-tag-files-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`

### Task 5. Commit And Push

- [ ] Stage only milestone files.
- [ ] Commit with:
  - `feat(skill): add owner preview tag files gate`
- [ ] Push to `dev`.

## Acceptance Criteria

- Tag file metadata remains Java-compatible and published-only.
- Owner/admin pending tag files still return the same Java/Python/Vite status.
- Published tag files match across Java, Python, Vite `/api/v1`, and Vite `/api/web`.
- Python tests, Vite proxy tests, TypeScript typecheck, and Windows live gate pass.
- `git diff --name-only -- server` is empty.
