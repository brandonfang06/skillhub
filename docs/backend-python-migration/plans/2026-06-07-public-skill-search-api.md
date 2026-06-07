# Public Skill Search API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate anonymous public portal skill search reads to FastAPI while preserving Java-owned
ClawHub compatibility routes.

**Architecture:** Python will own only `GET /api/web/skills`, the React portal search endpoint.
`GET /api/v1/skills` is a ClawHub compatibility list/publish surface and must remain Java-owned in
this milestone. Search reads use PostgreSQL tables only: `skill_search_document`, `skill`,
`namespace`, `skill_version`, and optional `skill_label` / `label_definition`.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, Windows
hybrid Java/Python/DB/Vite live contract comparison.

**Status:** Completed for anonymous public portal behavior on 2026-06-07. Result:
`docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md`.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/web/skills` | java | python |

This milestone explicitly does not migrate:

- `GET /api/v1/skills` because Java uses it for ClawHub compatibility list responses.
- `POST /api/v1/skills` because Java uses it for ClawHub compatibility publish.
- `GET /api/v1/search` ClawHub search.
- Any skill detail, nested version, file, download, lifecycle, social, auth, OAuth, or admin route.

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillSearchController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillSearchAppService.java`
- `server/skillhub-search/src/main/java/com/iflytek/skillhub/search/postgres/PostgresFullTextQueryService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillSummaryResponse.java`

Observed Java portal search contract:

- Route: `GET /api/web/skills`
- Query params:
  - `q`: optional keyword.
  - `namespace`: optional namespace slug.
  - `label`: optional repeated label slug.
  - `sort`: optional; default `newest`; supported observed values include `newest`, `downloads`,
    `rating`, `relevance`.
  - `page`: optional non-negative integer string; invalid values default to `0`.
  - `size`: optional positive integer string; invalid or zero values default to `20`.
- Response envelope: `ok("response.success.read", SearchResponse)`.
- Localized Java default `msg` is the same mojibake string currently returned by Python routes.
- Response data shape:
  - `items`: array of `SkillSummaryResponse`.
  - `total`: long.
  - `page`: requested normalized page.
  - `size`: requested normalized size.

Anonymous public visibility:

- `skill_search_document.visibility = 'PUBLIC'`.
- `skill_search_document.status = 'ACTIVE'`.
- `skill.status = 'ACTIVE'`.
- `skill.hidden = false`.
- `namespace.status <> 'ARCHIVED'`.

## Corrected Route Scope

The earlier sequence plan listed both `GET /api/v1/skills` and `GET /api/web/skills` as public skill
search. Local inspection shows this is incorrect:

- `/api/web/skills` is portal search.
- `/api/v1/skills` is Java ClawHub compatibility list/publish and returns `ClawHubSkillListResponse`
  for GET.

Therefore this milestone must keep `/api/v1/skills` Java-owned. The sequence plan and route
registry must be corrected before implementation is marked complete.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_search.py`
- `server-python/tests/test_skill_search_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-search-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Object storage integration code
- Auth/session/CSRF bridge code
- `/api/v1/skills` proxy ownership

## Route Ownership And Vite Proxy

Add only this exact proxy entry before `/api` fallback:

```ts
      '/api/web/skills': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
```

This entry must not change `/api/v1/skills`; Vite should keep `/api/v1/skills` on Java through the
generic `/api` fallback.

---

## Task 1: Search Response Builder Tests

**Files:**

- Create: `server-python/tests/test_skill_search_repository.py`
- Modify: `server-python/app/api/skills.py`

- [x] **Step 1: Write failing response mapping tests**

Create tests for Java-compatible `SkillSummaryResponse` field names and `SearchResponse` page
shape.

```python
from datetime import UTC, datetime
from decimal import Decimal

from app.api.skills import build_skill_search_response


def test_build_skill_search_response_maps_java_summary_fields() -> None:
    rows = [
        {
            "id": 31,
            "slug": "demo-skill",
            "display_name": "Demo Skill",
            "summary": "Demo summary",
            "visibility": "PUBLIC",
            "status": "ACTIVE",
            "download_count": 7,
            "star_count": 3,
            "rating_avg": Decimal("4.50"),
            "rating_count": 4,
            "namespace": "global",
            "updated_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
            "published_version_id": 41,
            "published_version": "1.2.0",
            "published_version_status": "PUBLISHED",
            "resolution_mode": "PUBLISHED",
        }
    ]

    assert build_skill_search_response(rows, total=1, page=0, size=20) == {
        "items": [
            {
                "id": 31,
                "slug": "demo-skill",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "visibility": "PUBLIC",
                "status": "ACTIVE",
                "downloadCount": 7,
                "starCount": 3,
                "ratingAvg": 4.5,
                "ratingCount": 4,
                "namespace": "global",
                "updatedAt": "2026-06-07T10:00:00Z",
                "canSubmitPromotion": False,
                "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "ownerPreviewVersion": None,
                "resolutionMode": "PUBLISHED",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }
```

- [x] **Step 2: Run builder test and confirm RED**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search_repository.py -v
```

Expected: FAIL because `build_skill_search_response` does not exist.

- [x] **Step 3: Implement minimal response builder**

Add `build_skill_summary_response` and `build_skill_search_response` beside the detail builder.
Use `to_java_instant` and `to_lifecycle_version` to keep lifecycle and timestamp behavior aligned.

- [x] **Step 4: Run builder test and confirm GREEN**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search_repository.py -v
```

Expected: PASS.

## Task 2: Route Tests

**Files:**

- Create: `server-python/tests/test_skill_search.py`
- Modify: `server-python/app/api/skills.py`

- [x] **Step 1: Write failing route tests**

Create tests for:

- `/api/web/skills` envelope.
- request id propagation.
- repeated `label` params.
- Java-style invalid `page` / `size` defaults.
- `/api/v1/skills` is not registered by this FastAPI router.

- [x] **Step 2: Run route tests and confirm RED**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search.py -v
```

Expected: FAIL with `404 Not Found` for `/api/web/skills`.

- [x] **Step 3: Add route handler**

Add:

```python
@router.get("/api/web/skills")
async def search_skills(...):
    ...
```

The route should call an injected `app.state.skill_search_reader` in tests, or
`read_skill_search(request.app.state.db_engine, ...)` in normal runtime.

- [x] **Step 4: Run route tests and confirm GREEN**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search.py -v
```

Expected: PASS.

## Task 3: PostgreSQL Search Reader

**Files:**

- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/tests/test_skill_search_repository.py`

- [x] **Step 1: Add unit tests for parameter normalization**

Cover:

- missing sort -> `newest`
- blank sort -> `newest`
- invalid page -> `0`
- invalid or zero size -> `20`
- label slugs trimmed, lowercased, deduplicated

- [x] **Step 2: Implement parameter helpers**

Add:

- `normalize_search_sort`
- `parse_non_negative_int`
- `parse_positive_int`
- `normalize_label_slugs`

- [x] **Step 3: Implement `read_skill_search`**

Use PostgreSQL query logic equivalent to Java's anonymous branch:

- Base from `skill_search_document d`.
- Join `skill s` and `namespace n`.
- Filter anonymous public visibility and active statuses.
- Optional namespace slug filter by resolving `namespace`.
- Optional label slug filter.
- Optional keyword filter using `d.search_vector @@ to_tsquery('simple', :ts_query)` plus
  `LOWER(d.title) LIKE :title_like`.
- Sort:
  - `downloads`: `s.download_count DESC, s.updated_at DESC, d.skill_id DESC`
  - `rating`: `s.rating_avg DESC, s.updated_at DESC, d.skill_id DESC`
  - `relevance` with keyword: title exact/prefix/contains, ts rank, updated desc, skill id desc
  - default/newest: `s.updated_at DESC, d.skill_id DESC`
- Pagination: `LIMIT :limit OFFSET :offset`.
- Count uses the same filters without ordering/limit.
- Summary projection should resolve published lifecycle version with the same rule as detail.

- [x] **Step 4: Run focused Python tests**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search.py tests/test_skill_search_repository.py -v
```

Expected: PASS.

## Task 4: Vite Proxy Ownership

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [x] **Step 1: Add proxy tests**

Assert:

- `/api/web/skills` routes to Python.
- `/api/web/skills?q=agent` routes to Python.
- `/api/v1/skills` remains Java.
- nested Python-owned routes still route to Python.
- `/api/v1/skills/global/demo/download` remains Java.

- [x] **Step 2: Run proxy tests and confirm RED**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: FAIL because `/api/web/skills` proxy is not yet Python-owned.

- [x] **Step 3: Add proxy entry and docs updates**

Add exact Vite proxy entry for `/api/web/skills` only. Update route registry and sequence plan to
show `/api/web/skills` as this milestone and `/api/v1/skills` as Java-owned ClawHub compatibility.

- [x] **Step 4: Run proxy tests and confirm GREEN**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: PASS.

## Task 5: Windows Live Contract Gate

**Files:**

- Modify: `scripts/dev-hybrid.ps1`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Create: `docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md`
- Modify: `docs/backend-python-migration/windows-live-verification.md`

- [x] **Step 1: Add `verify-search-smoke` action**

Extend `scripts/dev-hybrid.ps1` with a new gate that:

- starts Java, Python, Vite, PostgreSQL, Redis, MinIO, and scanner
- creates deterministic PostgreSQL fixture data including search documents
- compares Java direct `/api/web/skills`, Python direct `/api/web/skills`, and Vite
  `/api/web/skills`
- confirms Vite `/api/v1/skills` does not match portal search shape and remains Java-owned
- compares representative queries:
  - default newest page
  - `q=codex-search-fixture&sort=relevance`
  - `namespace=global`
  - repeated `label=codex-search-featured`
  - `sort=downloads`
  - `sort=rating`
  - invalid `page` / `size` normalization
- runs Playwright smoke
- stops the hybrid stack

- [x] **Step 2: Run live gate**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-search-smoke
```

Expected:

- Java/Python/Vite stable `code`, `msg`, and `data` match for all compared `/api/web/skills`
  cases.
- `/api/v1/skills` stays Java-owned.
- Playwright smoke passes.

- [x] **Step 3: Run final verification**

Run:

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

Expected:

- Python tests pass.
- Vite proxy tests pass.
- `git diff --check` has no whitespace errors.
- `git diff --name-only -- server` is empty.

- [x] **Step 4: Write result document**

Create `docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md` with:

- routes changed
- owner before/after
- implementation summary
- tests
- live Java/Python/proxy comparison summary
- route scope correction for `/api/v1/skills`
- risks and follow-up

- [ ] **Step 5: Commit and push**

Commit and push only after the result document is complete.

## Acceptance Criteria

- `GET /api/web/skills` is Python-owned in Vite dev.
- `GET /api/v1/skills` remains Java-owned.
- Anonymous public Java/Python/proxy search responses match for stable fields.
- Query params `q`, `namespace`, repeated `label`, `sort`, `page`, and `size` are covered.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `scripts\dev-hybrid.ps1 verify-search-smoke` passes on Windows.
- `git diff --name-only -- server` is empty.
- Result document is written before commit.
