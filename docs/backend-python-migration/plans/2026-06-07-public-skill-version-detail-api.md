# Public Skill Version Detail API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public read-only skill version detail API to FastAPI while Java and Python
continue to coexist.

**Architecture:** Python will own only the anonymous/public GET detail aliases for a concrete skill
version. The implementation extends the existing `skills` API module, reuses anonymous public skill
lookup from resolve/version-list milestones, returns Java-compatible `SkillVersionDetailResponse`,
and leaves compare, file metadata, file content, and download routes on Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, live
Java/Python/DB contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}` | java | python |

This milestone does not migrate:

- `DELETE /api/v1|web/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/compare`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/download`
- Authenticated owner/admin preview for non-published versions

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillVersionDetailResponse.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillQueryService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/SkillVersion.java`

Observed Java contract:

- Controller returns `ok("response.success.read", SkillVersionDetailResponse)`.
- Localized Java default `msg` is `获取成功`.
- Response fields:
  - `id`
  - `version`
  - `status`
  - `changelog`
  - `fileCount`
  - `totalSize`
  - `publishedAt`
  - `parsedMetadataJson`
  - `manifestJson`
- `parsedMetadataJson` and `manifestJson` are returned as strings, not parsed JSON objects.
- `publishedAt` is serialized as UTC ISO-8601, for example `2026-03-12T12:00:00Z`.
- Anonymous callers may inspect only `PUBLISHED` versions.
- Non-published version preview remains restricted to skill owner or namespace admin/owner and is
  deferred until the Python auth/session bridge exists.

Anonymous public access for Python requires:

- matching namespace slug
- `namespace.status = 'ACTIVE'`
- matching skill slug
- `skill.status = 'ACTIVE'`
- `skill.latest_version_id IS NOT NULL`
- `skill.hidden = false`
- `skill.visibility = 'PUBLIC'`
- requested version must have `status = 'PUBLISHED'`

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_version_detail.py`
- `server-python/tests/test_skill_version_detail_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-version-detail-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-version-detail-api.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Auth/session/OAuth/API token code
- Version compare, files, file content, download, storage, or rate-limit code

## Route Ownership And Vite Proxy

Add these exact regex proxy entries before the generic `/api` fallback:

```ts
'^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
'^/api/web/skills/[^/]+/[^/]+/versions/[^/]+$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
```

Do not add proxy entries for:

- `/versions/compare`
- `/versions/{version}/files`
- `/versions/{version}/file`
- `/versions/{version}/download`
- broad `/api/v1/skills` or `/api/web/skills`

## Task 1: Route Tests

**Files:**

- Create: `server-python/tests/test_skill_version_detail.py`

- [ ] **Step 1: Write failing route tests**

Add tests for both aliases and request id propagation:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def detail_response() -> dict[str, object]:
    return {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "fileCount": 2,
        "totalSize": 128,
        "publishedAt": "2026-06-07T10:00:00Z",
        "parsedMetadataJson": "{\"name\":\"demo\"}",
        "manifestJson": "[{\"path\":\"SKILL.md\"}]",
    }


def test_skill_version_detail_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_detail_reader = lambda namespace, slug, version: detail_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0",
        headers={"X-Request-Id": "version-detail-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "version-detail-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "version-detail-test"
    assert response.json()["data"] == detail_response()
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_version_detail.py -v
```

Expected failure: `404 Not Found` for both detail routes.

## Task 2: Pure Helper Tests

**Files:**

- Create: `server-python/tests/test_skill_version_detail_repository.py`
- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Write failing helper tests**

Add tests for Java field mapping and timestamp handling:

```python
from datetime import UTC, datetime

from app.api.skills import build_version_detail_response


def test_build_version_detail_response_maps_java_fields_and_json_strings() -> None:
    row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "file_count": 2,
        "total_size": 128,
        "published_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        "parsed_metadata_json": "{\"name\":\"demo\"}",
        "manifest_json": "[{\"path\":\"SKILL.md\"}]",
    }

    assert build_version_detail_response(row) == {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "fileCount": 2,
        "totalSize": 128,
        "publishedAt": "2026-06-07T10:00:00Z",
        "parsedMetadataJson": "{\"name\":\"demo\"}",
        "manifestJson": "[{\"path\":\"SKILL.md\"}]",
    }
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_version_detail_repository.py -v
```

Expected failure: missing `build_version_detail_response`.

## Task 3: Minimal FastAPI Implementation

**Files:**

- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Implement helper and route behavior**

Implementation requirements:

- Add route aliases:
  - `/api/v1/skills/{namespace}/{slug}/versions/{version}`
  - `/api/web/skills/{namespace}/{slug}/versions/{version}`
- Route handler remains thin.
- Support test injection via `app.state.skill_version_detail_reader`.
- Query the same anonymous public skill visibility rules as resolve/list.
- Select requested version by exact `version`.
- Require `skill_version.status = 'PUBLISHED'` for anonymous public behavior.
- Return Java-compatible detail fields exactly.

- [ ] **Step 2: Run focused Python tests and confirm GREEN**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_version_detail.py tests/test_skill_version_detail_repository.py -v
```

Expected: tests pass.

## Task 4: Vite Proxy And Registry

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`

- [ ] **Step 1: Add failing Vite proxy test expectations**

Add expectations that both exact `/versions/{version}` regex routes target Python before `/api`, while
compare, files, file, and download routes remain Java-owned by the fallback.

- [ ] **Step 2: Run frontend config test and confirm RED**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected failure: missing version detail proxy entries.

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

- Create: `docs/backend-python-migration/results/2026-06-07-public-skill-version-detail-api.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [ ] **Step 1: Start the hybrid stack**

Use the Windows single-lifecycle live gate pattern.

- [ ] **Step 2: Create or reuse a public fixture**

Fixture must have:

- active public namespace
- active public, non-hidden skill
- published version `1.2.0`
- non-published version `2.0.0-draft`
- parsed metadata JSON string
- manifest JSON string

- [ ] **Step 3: Compare Java, Python, and Vite proxy**

Stable comparison fields:

- `code`
- `msg`
- `data`

Scenarios:

- published version detail returns identical data
- Vite `/api/v1` and `/api/web` aliases match direct Python
- non-published version returns bad request from Java/Python/proxy

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

- Both version detail GET routes are Python-owned in Vite dev proxy.
- Both aliases return Java-compatible envelope and detail fields.
- Python returns anonymous public `PUBLISHED` version details only.
- Compare, files, file content, download, and DELETE routes remain Java-owned.
- Java/Python/proxy stable contract comparison passes.
- Frontend smoke E2E passes.
- `git diff --name-only -- server` returns empty output.
- Result document is written before commit.
- Milestone is committed and pushed to `dev`.

## Risks

- Python has no auth/session bridge, so owner/admin preview of non-published versions remains
  deferred.
- Exact Java error envelope for not-published versions is not implemented in Python yet; live gate
  requires status parity and records body differences if present.
- The regex proxy for `/versions/{version}` must not capture `/versions/{version}/files`,
  `/file`, or `/download`.
