# ClawHub Skills List API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Group A public catalog read ownership by migrating `GET /api/v1/skills` ClawHub
list to FastAPI while keeping publish, delete, undelete, download, auth, and mutation routes
Java-owned.

**Architecture:** This is the first pre-launch group-style milestone after the strategy change.
Python will own the remaining read-only ClawHub public catalog route and reuse the existing
PostgreSQL public skill search reader where the Java list route delegates to the Java search
service. Vite route ownership must keep method collisions explicit: `GET /api/v1/skills` goes to
Python, but `POST /api/v1/skills` remains Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite method-aware proxy,
Windows hybrid Java/Python/DB/Vite live contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills` | java | python |

This milestone does not migrate:

- `POST /api/v1/skills`
- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`
- file content/download routes under `/api/v1/skills/{namespace}/{slug}/...`
- auth, OAuth, session, token, lifecycle, publish, governance, or admin routes

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/dto/ClawHubSkillListResponse.java`

Observed Java contract:

- Route: `GET /api/v1/skills`
- Query parameters:
  - `page`, default `0`
  - `limit`, default `25`
  - `sort`, default `newest`
- Response is plain JSON:
  - `items`: array
  - `nextCursor`: string page number or `null`
- No `code`, `msg`, `data`, `requestId`, or `timestamp` envelope.

Java item fields:

- `slug`: canonical slug (`global` namespace maps to plain slug; other namespaces map to
  `{namespace}--{slug}`).
- `displayName`
- `summary`
- `tags`: currently `{}`.
- `stats`: object containing `downloads` and/or `stars` when source counts are non-null.
- `createdAt`: currently `0` in Java list mapper.
- `updatedAt`: skill summary `updatedAt` epoch milliseconds or `0`.
- `latestVersion`: object or `null`.

Java `latestVersion` fields:

- `version`
- `createdAt`: Java list mapper uses item `updatedAt`.
- `changelog`: currently empty string.
- `license`: currently `null`.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_clawhub_skills_list.py`
- `server-python/tests/test_clawhub_skills_list_repository.py`
- `server-python/tests/test_clawhub_search.py`
- `server-python/tests/test_skill_search.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-08-clawhub-skills-list-api.md`
- `docs/backend-python-migration/results/2026-06-08-clawhub-skills-list-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- auth/session/CSRF bridge code
- publish/upload logic
- download/file content logic

## Route Ownership Matrix

| Method | Path | Expected Owner After |
| --- | --- | --- |
| GET | `/api/v1/skills` | python |
| POST | `/api/v1/skills` | java |
| GET | `/api/v1/skills/{canonicalSlug}` | python |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java |
| GET | `/api/v1/download/{canonicalSlug}` | java |

## Tasks

- [x] **Step 1: Write failing ClawHub list mapper tests**

Create `server-python/tests/test_clawhub_skills_list_repository.py` covering:

- plain ClawHub list shape with `items` and `nextCursor`.
- canonical slug mapping.
- `stats.downloads` and `stats.stars`.
- `createdAt = 0`.
- `updatedAt` epoch milliseconds.
- `latestVersion.createdAt` equals `updatedAt`.
- `latestVersion.changelog = ""` and `license = None`.
- no SkillHub `ApiResponse` fields.

- [x] **Step 2: Confirm RED for mapper tests**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_skills_list_repository.py -v
```

Expected: FAIL because `build_clawhub_skills_list_response` does not exist.

- [x] **Step 3: Implement ClawHub list mapper**

Add `build_clawhub_skills_list_response(search_response)` in
`server-python/app/api/skills.py`.

- [x] **Step 4: Write failing route tests**

Create `server-python/tests/test_clawhub_skills_list.py` covering:

- `GET /api/v1/skills` returns plain ClawHub list JSON.
- query parameters `page`, `limit`, and `sort` forward to the search reader.
- `POST /api/v1/skills` remains unowned by Python.
- `GET /api/v1/skills/{canonicalSlug}` still returns ClawHub detail shape.

- [x] **Step 5: Confirm RED for route tests**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_skills_list.py -v
```

Expected: FAIL for `GET /api/v1/skills` because the route does not exist yet.

- [x] **Step 6: Implement route**

Add `GET /api/v1/skills` route before `GET /api/v1/skills/{canonicalSlug}`. It should:

- normalize `page` to non-negative integer.
- normalize `limit` to positive integer, defaulting invalid values to `25`.
- use `sort` default `newest`.
- call injected `app.state.clawhub_skills_list_reader` when present.
- otherwise call `read_skill_search` with empty keyword, no namespace, no labels, requested sort,
  page, and limit.
- return plain ClawHub list response.

- [x] **Step 7: Update Vite method-aware ownership**

Add a method-aware rule for `GET /api/v1/skills(?:?...)?` to Python. Keep:

- `POST /api/v1/skills` Java fallback.
- `DELETE /api/v1/skills/{canonicalSlug}` Java fallback.
- `POST /api/v1/skills/{canonicalSlug}/undelete` Java fallback.

- [x] **Step 8: Add Windows live gate**

Add `verify-clawhub-list-smoke` to `scripts/dev-hybrid.ps1`. It should reuse deterministic search
fixtures and compare Java/Python/Vite for:

- `/api/v1/skills?page=0&limit=5&sort=newest`
- `/api/v1/skills?page=0&limit=5&sort=downloads`
- `/api/v1/skills?page=0&limit=5&sort=rating`

It must also confirm:

- `POST /api/v1/skills` through Vite matches Java status behavior.
- `DELETE /api/v1/skills/{canonicalSlug}` through Vite matches Java status behavior.
- `GET /api/v1/download/{canonicalSlug}` remains Java redirect behavior.
- Playwright smoke passes.

- [x] **Step 9: Update docs**

Update:

- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

- [x] **Step 10: Final verification**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
cd ..\web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
.\node_modules\.bin\tsc.CMD --noEmit
cd ..
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-list-smoke
git diff --check
git diff --name-only -- server
```

- [x] **Step 11: Write result document**

Create `docs/backend-python-migration/results/2026-06-08-clawhub-skills-list-api.md`.

- [x] **Step 12: Commit and push**

Commit and push after verification and result document are complete.

## Acceptance Criteria

- `GET /api/v1/skills` is Python-owned in Vite dev.
- Response is plain ClawHub JSON, not `ApiResponse`.
- Root `POST /api/v1/skills` remains Java-owned.
- `DELETE /api/v1/skills/{canonicalSlug}` remains Java-owned.
- `GET /api/v1/download/{canonicalSlug}` remains Java-owned.
- Java/Python/Vite live contract comparison passes for representative list sorts.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `cd web; .\node_modules\.bin\tsc.CMD --noEmit` passes.
- `git diff --name-only -- server` is empty.
