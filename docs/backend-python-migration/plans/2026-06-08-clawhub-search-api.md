# ClawHub Search API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `GET /api/v1/search` ClawHub compatibility search to FastAPI while preserving
Java-owned ClawHub list, publish, resolve, and download routes.

**Architecture:** Python will expose a plain ClawHub response, not the portal `ApiResponse`
envelope. The route reuses the anonymous public portal search reader and maps `SkillSummaryResponse`
items into `ClawHubSearchResponse` shape.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, Windows
hybrid Java/Python/DB/Vite live contract comparison.

**Status:** Completed for anonymous public ClawHub compatibility behavior on 2026-06-08. Result:
`docs/backend-python-migration/results/2026-06-08-clawhub-search-api.md`.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/search` | java | python |

This milestone does not migrate:

- `GET /api/v1/skills`
- `POST /api/v1/skills`
- `GET /api/v1/resolve`
- `GET /api/v1/resolve/{canonicalSlug}`
- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`
- any portal `/api/web/**` route already handled by previous milestones

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/dto/ClawHubSearchResponse.java`

Observed Java contract:

- Route: `GET /api/v1/search`
- Query params:
  - `q`: required keyword.
  - `page`: optional integer, default `0`.
  - `limit`: optional integer, default `20`.
- Sort behavior:
  - If `q` is blank, Java uses `newest`.
  - Otherwise Java uses `relevance`.
- Response is plain JSON:
  - `results`: array.
  - Each result has `slug`, `displayName`, `summary`, `version`, `score`, `updatedAt`.
- No `code`, `msg`, `data`, `requestId`, or `timestamp` envelope.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_clawhub_search.py`
- `server-python/tests/test_clawhub_search_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-08-clawhub-search-api.md`
- `docs/backend-python-migration/results/2026-06-08-clawhub-search-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- `/api/v1/skills` proxy ownership
- auth/session/CSRF bridge code

## Tasks

- [x] **Step 1: Write failing ClawHub response mapping tests**

Create `server-python/tests/test_clawhub_search_repository.py` covering canonical slug mapping,
score calculation, updatedAt epoch millis, and plain response shape.

- [x] **Step 2: Run repository tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_search_repository.py -v
```

- [x] **Step 3: Implement ClawHub response mapper**

Add helper functions in `server-python/app/api/skills.py`:

- `to_clawhub_canonical_slug(namespace, slug)`
- `build_clawhub_search_response(search_response)`

- [x] **Step 4: Write failing route tests**

Create `server-python/tests/test_clawhub_search.py` covering:

- `/api/v1/search?q=...` returns plain JSON.
- route forwards `q`, `page`, `limit`, and computed sort.
- `/api/v1/skills` remains unowned by Python.

- [x] **Step 5: Run route tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_search.py -v
```

- [x] **Step 6: Implement route**

Add `GET /api/v1/search` route. It should call injected `app.state.clawhub_search_reader` in tests
or `read_skill_search` in runtime, then map to ClawHub response.

- [x] **Step 7: Run focused Python tests**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_search.py tests/test_clawhub_search_repository.py -v
```

- [x] **Step 8: Add Vite proxy tests and route ownership**

Proxy only `/api/v1/search` to Python. Keep `/api/v1/skills`, `/api/v1/resolve`, and
`/api/v1/download` on Java.

- [x] **Step 9: Add Windows live gate**

Add `verify-clawhub-search-smoke` to `scripts/dev-hybrid.ps1`. It should reuse deterministic search
fixtures, compare Java/Python/Vite `/api/v1/search?q=codex-search-alpha-unique&page=0&limit=5`,
confirm plain ClawHub shape, confirm `/api/v1/skills` remains Java-owned, run Playwright smoke,
and stop the hybrid stack.

- [x] **Step 10: Final verification**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
cd ..
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
cd ..
git diff --check
git diff --name-only -- server
```

- [x] **Step 11: Write result document**

Create `docs/backend-python-migration/results/2026-06-08-clawhub-search-api.md`.

- [x] **Step 12: Commit and push**

Commit and push after verification and result document are complete.

## Acceptance Criteria

- `GET /api/v1/search` is Python-owned in Vite dev.
- Response is plain ClawHub JSON, not `ApiResponse`.
- `/api/v1/skills` remains Java-owned.
- Java/Python/Vite live contract comparison passes.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `git diff --name-only -- server` is empty.
