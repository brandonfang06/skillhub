# Public Skill Versions List API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public read-only skill versions list API to FastAPI while Java and Python
continue to coexist.

**Architecture:** Python will own only the anonymous/public GET list aliases for skill versions.
The implementation reuses the `skills` API module and PostgreSQL access from the resolve milestone,
returns Java-compatible `PageResponse<SkillVersionResponse>`, and leaves version detail, file
metadata, file content, and downloads on Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, live
Java/Python/DB contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions` | java | python |

This milestone does not migrate:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/compare`
- Authenticated owner preview, private/namespace-only visibility, hidden preview, and SUPER_ADMIN
  bypass

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillVersionResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/PageResponse.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillQueryService.java`

Observed Java contract:

- Controller returns `ok("response.success.read", PageResponse<SkillVersionResponse>)`.
- Localized Java default `msg` is `获取成功`.
- Query params:
  - `page`, default `0`
  - `size`, default `20`
- `PageResponse` fields:
  - `items`
  - `total`
  - `page`
  - `size`
- `SkillVersionResponse` fields:
  - `id`
  - `version`
  - `status`
  - `changelog`
  - `fileCount`
  - `totalSize`
  - `publishedAt`
  - `downloadAvailable`
- For anonymous callers, Java returns only versions with `status = 'PUBLISHED'`.
- For manager callers, Java can return draft, pending review, uploaded, rejected, yanked, scanning,
  and scan-failed versions. This behavior remains Java-owned/deferred until the auth/session bridge
  exists.
- `downloadAvailable` is true only when the version status is `PUBLISHED` and `download_ready` is
  true.

Anonymous public access for Python requires:

- matching namespace slug
- `namespace.status = 'ACTIVE'`
- matching skill slug
- `skill.status = 'ACTIVE'`
- `skill.latest_version_id IS NOT NULL`
- `skill.hidden = false`
- `skill.visibility = 'PUBLIC'`
- returned versions must have `status = 'PUBLISHED'`

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_versions.py`
- `server-python/tests/test_skill_versions_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-versions-list-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-versions-list-api.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Auth/session/OAuth/API token code
- Version detail, compare, file metadata, file content, download, storage, or rate-limit code

## Route Ownership And Vite Proxy

Add these exact regex proxy entries before the generic `/api` fallback:

```ts
'^/api/v1/skills/[^/]+/[^/]+/versions$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
'^/api/web/skills/[^/]+/[^/]+/versions$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
```

Do not add a broad `/api/v1/skills` or `/api/web/skills` proxy entry.

## Task 1: Route Tests

**Files:**

- Create: `server-python/tests/test_skill_versions.py`

- [ ] **Step 1: Write failing route tests**

Add tests for both aliases and selector forwarding:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_skill_versions_v1_route_returns_page_envelope() -> None:
    app = create_app()
    app.state.skill_versions_reader = lambda namespace, slug, page, size: {
        "items": [
            {
                "id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "changelog": "latest",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-07T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": page,
        "size": size,
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions",
        params={"page": 0, "size": 20},
        headers={"X-Request-Id": "versions-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "versions-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "versions-test"
    assert response.json()["data"]["items"][0]["version"] == "1.2.0"
    assert response.json()["data"]["total"] == 1
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_versions.py -v
```

Expected failure: `404 Not Found` for both versions list routes.

## Task 2: Pure Helper Tests

**Files:**

- Create: `server-python/tests/test_skill_versions_repository.py`
- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Write failing helper tests**

Add tests for Java-compatible paging and response shaping:

```python
from app.api.skills import build_versions_page_response, paginate_rows


def test_paginate_rows_uses_zero_based_page_and_size() -> None:
    rows = [{"id": value} for value in range(1, 6)]

    assert paginate_rows(rows, page=1, size=2) == ([{"id": 3}, {"id": 4}], 5)


def test_build_versions_page_response_maps_java_field_names() -> None:
    rows = [
        {
            "id": 20,
            "version": "1.2.0",
            "status": "PUBLISHED",
            "changelog": "latest",
            "file_count": 2,
            "total_size": 128,
            "published_at": "2026-06-07T10:00:00Z",
            "download_ready": True,
        }
    ]

    assert build_versions_page_response(rows, total=1, page=0, size=20) == {
        "items": [
            {
                "id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "changelog": "latest",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-07T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_versions_repository.py -v
```

Expected failure: missing helper functions.

## Task 3: Minimal FastAPI Implementation

**Files:**

- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Implement helper and route behavior**

Implementation requirements:

- Add route aliases:
  - `/api/v1/skills/{namespace}/{slug}/versions`
  - `/api/web/skills/{namespace}/{slug}/versions`
- Accept `page: int = 0`, `size: int = 20`.
- Clamp negative `page` to `0`; clamp `size < 1` to `20`; cap very large `size` at `100`.
- Support test injection via `app.state.skill_versions_reader`.
- Query the same anonymous public skill visibility rules as resolve.
- Return only `skill_version.status = 'PUBLISHED'`.
- Order by `created_at DESC` to match Java `SkillVersionJpaRepository.findBySkillIdAndStatus()`.
- Map `downloadAvailable = status == 'PUBLISHED' and download_ready == true`.

- [ ] **Step 2: Run focused Python tests and confirm GREEN**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_versions.py tests/test_skill_versions_repository.py -v
```

Expected: tests pass.

## Task 4: Vite Proxy And Registry

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`

- [ ] **Step 1: Add failing Vite proxy test expectations**

Add expectations that both exact `/versions` list regex routes target Python before `/api`, while
`/versions/{version}`, `/versions/compare`, `/versions/{version}/files`, `/file`, and `/download`
remain Java-owned by the fallback.

- [ ] **Step 2: Run frontend config test and confirm RED**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected failure: missing versions list proxy entries.

- [ ] **Step 3: Add proxy entries and registry rows**

Add both exact proxy entries before `/api` and add both routes to the registry as Python-owned.

- [ ] **Step 4: Run frontend config test and confirm GREEN**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: pass.

## Task 5: Live Contract Verification

**Files:**

- Create: `docs/backend-python-migration/results/2026-06-07-public-skill-versions-list-api.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [ ] **Step 1: Start the hybrid stack**

Use the Windows single-lifecycle live gate pattern:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

- [ ] **Step 2: Create or reuse a public fixture**

Fixture must have:

- active public namespace
- active public, non-hidden skill
- at least two published versions
- at least one non-published version to prove anonymous filtering
- `download_ready` true on one published version and false on another

- [ ] **Step 3: Compare Java, Python, and Vite proxy**

Stable comparison fields:

- `code`
- `msg`
- `data.items`
- `data.total`
- `data.page`
- `data.size`

Scenarios:

- default `page=0,size=20`
- explicit `page=0,size=1`
- explicit `page=1,size=1`
- Vite proxy `/api/v1` and `/api/web` aliases match direct Python

Ignore volatile fields:

- `timestamp`
- `requestId`

- [ ] **Step 4: Run smoke E2E**

```powershell
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts
```

- [ ] **Step 5: Run final checks**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
cd ..
git diff --name-only -- server
git diff --check
```

Expected:

- Python tests pass.
- Vite config test passes.
- Live Java/Python/proxy comparison passes.
- E2E smoke passes.
- `git diff --name-only -- server` returns empty output.
- `git diff --check` has no whitespace errors.

## Acceptance Criteria

- Both versions list GET routes are Python-owned in Vite dev proxy.
- Both aliases return Java-compatible envelope and page fields.
- Python returns anonymous public `PUBLISHED` versions only.
- Version detail, compare, file, and download routes remain Java-owned.
- Java/Python/proxy stable contract comparison passes for default and paginated scenarios.
- Frontend smoke E2E passes.
- `git diff --name-only -- server` returns empty output.
- Result document is written before commit.
- Milestone is committed and pushed to `dev`.

## Risks

- Anonymous Java ordering for published versions comes from the infra repository default method:
  `created_at DESC`.
- Python has no auth/session bridge, so manager-visible non-published versions remain deferred.
- Future version detail/file milestones should reuse the same public skill lookup and published
  version filtering, but must not be grouped into this list milestone.
