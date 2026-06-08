# ClawHub Skill Detail API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `GET /api/v1/skills/{canonicalSlug}` ClawHub compatibility skill detail to
FastAPI while keeping ClawHub list, publish, delete, undelete, download, and nested SkillHub routes
Java-owned.

**Architecture:** Python will expose plain ClawHub skill detail JSON for one-segment canonical slug
requests only. The implementation reuses the existing anonymous public `read_skill_detail` reader,
adds ClawHub response mapping, and uses exact Vite regex routing so `/api/v1/skills`,
`/api/v1/skills/{namespace}/{slug}`, and deeper paths keep their existing owners.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, Windows
hybrid Java/Python/DB/Vite live contract comparison.

**Status:** Blocked before implementation. This route shares the same path with Java-owned
`DELETE /api/v1/skills/{canonicalSlug}`. Current Vite proxy ownership is path-based, so a plain
regex proxy would also route DELETE to Python. Complete
`docs/backend-python-migration/plans/2026-06-08-method-aware-vite-proxy.md` before implementing
this API.

## Blocker

Do not implement this API until method-aware Vite proxy routing exists and is verified.

Reason:

- `GET /api/v1/skills/{canonicalSlug}` should be Python-owned.
- `DELETE /api/v1/skills/{canonicalSlug}` must remain Java-owned.
- Vite `server.proxy` entries match path, not HTTP method.
- A regex-only proxy would violate the migration boundary by sending Java-owned DELETE requests to
  Python.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{canonicalSlug}` | java | python |

This milestone does not migrate:

- `GET /api/v1/skills`
- `POST /api/v1/skills`
- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/v1/skills/{namespace}/{slug}/**`
- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`
- any star, publish, delete, whoami, auth, OAuth, or session route

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/CanonicalSlugMapper.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/dto/ClawHubSkillResponse.java`

Observed Java contract:

- Route: `GET /api/v1/skills/{canonicalSlug}`
- Canonical slug mapping:
  - no `--`: namespace `global`, skill slug is the whole value.
  - first `--`: namespace is the prefix, skill slug is the suffix.
- Response is plain JSON:
  - `skill`: object or `null`.
  - `latestVersion`: object or `null`.
  - `owner`: currently `null`.
  - `moderation`: object with clean/default scanner fields.
- No `code`, `msg`, `data`, `requestId`, or `timestamp` envelope.

Java `skill` object fields:

- `slug`: canonical slug.
- `displayName`
- `summary`
- `tags`: currently `{}`.
- `stats`: currently `{}`.
- `createdAt`: epoch millis, Java uses `0` when absent.
- `updatedAt`: epoch millis, Java uses `0` when absent.

Java `latestVersion` object fields:

- `version`
- `createdAt`: latest version `publishedAt` epoch millis, or `0`.
- `changelog`: empty string when Java changelog is `null`.
- `license`: currently `null`.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_clawhub_skill_detail.py`
- `server-python/tests/test_clawhub_skill_detail_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-08-clawhub-skill-detail-api.md`
- `docs/backend-python-migration/results/2026-06-08-clawhub-skill-detail-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- `/api/v1/skills` root proxy ownership
- `/api/v1/skills/{namespace}/{slug}` nested route ownership changes
- `/api/v1/download` proxy ownership
- auth/session/CSRF bridge code

## Tasks

- [ ] **Step 1: Write failing ClawHub skill detail mapping tests**

Create `server-python/tests/test_clawhub_skill_detail_repository.py` covering:

- canonical slug mapping from existing helpers.
- plain ClawHub response shape.
- stats and tags are empty maps.
- `latestVersion.createdAt` uses epoch milliseconds from `publishedAt`.
- `latestVersion.changelog` uses empty string when absent.
- no portal `ApiResponse` fields.

- [ ] **Step 2: Run repository tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_skill_detail_repository.py -v
```

Expected: FAIL because `build_clawhub_skill_detail_response` does not exist.

- [ ] **Step 3: Implement ClawHub response mapper**

Add `build_clawhub_skill_detail_response(detail_response)` in
`server-python/app/api/skills.py`.

- [ ] **Step 4: Write failing route tests**

Create `server-python/tests/test_clawhub_skill_detail.py` covering:

- `/api/v1/skills/demo` returns plain ClawHub JSON.
- `/api/v1/skills/team-ai--demo` parses canonical slug.
- `/api/v1/skills` remains unowned by Python.
- `/api/v1/skills/global/demo` continues to use the existing nested SkillHub route shape.
- `/api/v1/skills/demo/undelete` remains unowned by Python.

- [ ] **Step 5: Run route tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_skill_detail.py -v
```

Expected: FAIL for `/api/v1/skills/demo` because the ClawHub route does not exist yet.

- [ ] **Step 6: Implement route**

Add `GET /api/v1/skills/{canonicalSlug}` route before the nested
`/api/v1/skills/{namespace}/{slug}` route. It should:

- Parse canonical slug with `from_clawhub_canonical_slug`.
- Use injected `app.state.clawhub_skill_detail_reader` in tests when present.
- Otherwise call `read_skill_detail`.
- Return plain ClawHub response, not envelope.

- [ ] **Step 7: Run focused Python tests**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_clawhub_skill_detail.py tests/test_clawhub_skill_detail_repository.py -v
```

Expected: PASS.

- [ ] **Step 8: Add Vite proxy tests and route ownership**

Proxy only exact one-segment `GET /api/v1/skills/{canonicalSlug}` to Python. Keep:

- `/api/v1/skills`
- `/api/v1/skills/{namespace}/{slug}`
- `/api/v1/skills/{canonicalSlug}/undelete`
- `/api/v1/download/**`

on their existing owners.

- [ ] **Step 9: Add Windows live gate**

Add `verify-clawhub-skill-smoke` to `scripts/dev-hybrid.ps1`. It should reuse deterministic search
fixtures and compare Java/Python/Vite for:

- `/api/v1/skills/codex-search-alpha-20260607233000`

It must confirm:

- Java/Python/Vite stable plain JSON contracts match.
- `/api/v1/skills` remains Java-owned ClawHub list shape.
- `/api/v1/download/{canonicalSlug}` remains Java-owned redirect behavior.
- Playwright smoke passes.
- The hybrid stack is stopped after verification.

- [ ] **Step 10: Final verification**

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

- [ ] **Step 11: Write result document**

Create `docs/backend-python-migration/results/2026-06-08-clawhub-skill-detail-api.md`.

- [ ] **Step 12: Commit and push**

Commit and push after verification and result document are complete.

## Acceptance Criteria

- `GET /api/v1/skills/{canonicalSlug}` is Python-owned in Vite dev.
- Response is plain ClawHub JSON, not `ApiResponse`.
- `/api/v1/skills` remains Java-owned.
- Nested `/api/v1/skills/{namespace}/{slug}` remains the existing SkillHub route shape.
- `/api/v1/download/**` remains Java-owned.
- Java/Python/Vite live contract comparison passes.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `git diff --name-only -- server` is empty.
