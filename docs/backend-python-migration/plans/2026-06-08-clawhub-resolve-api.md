# ClawHub Resolve API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate ClawHub compatibility resolve routes to FastAPI while keeping download, publish,
list, skill detail, and auth-sensitive compatibility routes Java-owned.

**Architecture:** Python will expose plain ClawHub resolve JSON for `GET /api/v1/resolve` and
`GET /api/v1/resolve/{canonicalSlug}`. The route reuses existing anonymous public
`read_skill_resolve` behavior, adds canonical slug parsing and legacy query slug resolution, and
keeps `/api/v1/download/**`, `/api/v1/skills`, and `/api/v1/skills/{canonicalSlug}` on Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, Windows
hybrid Java/Python/DB/Vite live contract comparison.

**Status:** Completed for anonymous public ClawHub compatibility behavior on 2026-06-08. Result:
`docs/backend-python-migration/results/2026-06-08-clawhub-resolve-api.md`.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/resolve?slug=...` | java | python |
| GET | `/api/v1/resolve/{canonicalSlug}` | java | python |

This milestone does not migrate:

- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`
- `GET /api/v1/skills`
- `POST /api/v1/skills`
- `GET /api/v1/skills/{canonicalSlug}`
- any star, publish, delete, whoami, auth, OAuth, or session route

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/CanonicalSlugMapper.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/dto/ClawHubResolveResponse.java`

Observed Java contract:

- `GET /api/v1/resolve`
  - Query params:
    - `slug`: required.
    - `version`: optional.
    - `hash`: optional.
  - If `slug` contains `--`, Java treats it as canonical `{namespace}--{slug}`.
  - If `slug` does not contain `--`, Java first attempts legacy global slug lookup, then falls
    back to canonical global `{namespace=global, slug}`.
  - Java converts `version=latest` to tag selector `latest`.
- `GET /api/v1/resolve/{canonicalSlug}`
  - Query params:
    - `version`: optional, default `latest`.
  - Canonical slug mapping:
    - no `--`: namespace `global`, skill slug is the whole value.
    - first `--`: namespace is the prefix, skill slug is the suffix.
  - Java does not accept `hash` on this path.
- Response is plain JSON:
  - `match`: `{"version": "..."}` or `null`.
  - `latestVersion`: `{"version": "..."}` or `null`.
- No `code`, `msg`, `data`, `requestId`, or `timestamp` envelope.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_clawhub_resolve.py`
- `server-python/tests/test_clawhub_resolve_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-08-clawhub-resolve-api.md`
- `docs/backend-python-migration/results/2026-06-08-clawhub-resolve-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- `/api/v1/download` proxy ownership
- `/api/v1/skills` proxy ownership
- `/api/v1/skills/{canonicalSlug}` proxy ownership
- auth/session/CSRF bridge code

## Tasks

- [x] **Step 1: Write failing canonical slug and response mapping tests**

Create `server-python/tests/test_clawhub_resolve_repository.py` covering:

- `from_clawhub_canonical_slug("demo") == ("global", "demo")`
- `from_clawhub_canonical_slug("team-ai--demo") == ("team-ai", "demo")`
- first separator only: `team--demo--extra` maps to namespace `team`, slug `demo--extra`
- `build_clawhub_resolve_response` maps existing portal resolve data into plain
  `{match, latestVersion}` shape.

- [x] **Step 2: Run repository tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_resolve_repository.py -v
```

Expected: FAIL because ClawHub resolve helper functions do not exist.

- [x] **Step 3: Implement canonical slug and response helpers**

Add helper functions in `server-python/app/api/skills.py`:

- `from_clawhub_canonical_slug(canonical_slug)`
- `build_clawhub_resolve_response(resolve_response)`

- [x] **Step 4: Write failing route tests**

Create `server-python/tests/test_clawhub_resolve.py` covering:

- `/api/v1/resolve?slug=demo&version=latest` returns plain JSON.
- `/api/v1/resolve/team-ai--demo?version=1.2.0` parses canonical slug.
- query route forwards `hash`.
- `/api/v1/download/demo` remains unowned by Python.
- `/api/v1/skills/demo` remains unowned by Python.

- [x] **Step 5: Run route tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_resolve.py -v
```

Expected: FAIL with `404 Not Found` for `/api/v1/resolve`.

- [x] **Step 6: Implement routes**

Add:

- `GET /api/v1/resolve`
- `GET /api/v1/resolve/{canonicalSlug}`

The query route should:

- Parse `slug` as canonical when it contains `--`.
- Otherwise use injected `app.state.clawhub_legacy_slug_reader` when present, falling back to
  global canonical slug if the reader is absent.
- Convert `version=latest` to `tag=latest`.
- Forward query `hash` to `read_skill_resolve`.

The path route should:

- Parse `{canonicalSlug}` with `from_clawhub_canonical_slug`.
- Convert missing or `latest` version to `tag=latest`.
- Not accept or forward `hash`.

- [x] **Step 7: Run focused Python tests**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_resolve.py tests/test_clawhub_resolve_repository.py -v
```

Expected: PASS.

- [x] **Step 8: Add Vite proxy tests and route ownership**

Proxy only exact `/api/v1/resolve` and exact one-segment `/api/v1/resolve/{canonicalSlug}` to
Python. Keep `/api/v1/download`, `/api/v1/download/{canonicalSlug}`, `/api/v1/skills`, and
`/api/v1/skills/{canonicalSlug}` on Java.

- [x] **Step 9: Add Windows live gate**

Add `verify-clawhub-resolve-smoke` to `scripts/dev-hybrid.ps1`. It should reuse deterministic
search fixtures, compare Java/Python/Vite for:

- query form: `/api/v1/resolve?slug=codex-search-alpha-20260607233000&version=latest`
- path form: `/api/v1/resolve/codex-search-alpha-20260607233000?version=latest`

It must confirm:

- Java/Python/Vite stable plain JSON contracts match.
- `/api/v1/download/{canonicalSlug}` remains Java-owned redirect behavior.
- `/api/v1/skills/{canonicalSlug}` remains Java-owned ClawHub skill response behavior.
- Playwright smoke passes.
- The hybrid stack is stopped after verification.

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

Create `docs/backend-python-migration/results/2026-06-08-clawhub-resolve-api.md`.

- [x] **Step 12: Commit and push**

Commit and push after verification and result document are complete.

## Acceptance Criteria

- `GET /api/v1/resolve` is Python-owned in Vite dev.
- `GET /api/v1/resolve/{canonicalSlug}` is Python-owned in Vite dev.
- Responses are plain ClawHub JSON, not `ApiResponse`.
- `/api/v1/download/**`, `/api/v1/skills`, and `/api/v1/skills/{canonicalSlug}` remain Java-owned.
- Java/Python/Vite live contract comparison passes for query and path forms.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `git diff --name-only -- server` is empty.
