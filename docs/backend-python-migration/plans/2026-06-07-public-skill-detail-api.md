# Public Skill Detail API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate anonymous public skill detail reads to FastAPI while Java and Python continue to
coexist.

**Architecture:** Python will own only the anonymous/public GET aliases for skill detail. The route
will assemble the same read model Java returns for unauthenticated public viewers, using PostgreSQL
only. Authenticated owner/admin preview behavior, lifecycle mutations, social mutations, file
content, downloads, and search remain Java-owned.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, Windows
hybrid Java/Python/DB/Vite live contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}` | java | python |

This milestone does not migrate:

- `GET /api/v1|web/skills` search/list routes
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/**` routes already not part of detail
- file content routes ending in `/file`
- download routes ending in `/download`
- version compare routes
- publish/review/archive/yank/hide/restore/delete lifecycle mutations
- star/rate/subscribe/report mutations
- authenticated owner/admin preview semantics

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`
  lines 72-113
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillQueryService.java`
  lines 196-252
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillLifecycleProjectionService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillDetailResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLifecycleVersionResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLabelDto.java`

Observed Java response contract:

- Controller returns `ok("response.success.read", SkillDetailResponse)`.
- Localized Java default `msg` is `?瑕???`.
- Response fields:
  - `id`
  - `slug`
  - `displayName`
  - `ownerId`
  - `ownerDisplayName`
  - `summary`
  - `visibility`
  - `status`
  - `downloadCount`
  - `starCount`
  - `subscriptionCount`
  - `ratingAvg`
  - `ratingCount`
  - `hidden`
  - `namespace`
  - `labels`
  - `canManageLifecycle`
  - `canSubmitPromotion`
  - `canInteract`
  - `canReport`
  - `headlineVersion`
  - `publishedVersion`
  - `ownerPreviewVersion`
  - `ownerPreviewReviewComment`
  - `resolutionMode`

Anonymous public viewer behavior for the first Python milestone:

- `canManageLifecycle = false`
- `canSubmitPromotion = false`
- `canInteract = true` when the public headline version is published
- `canReport = true`
- `ownerPreviewVersion = null`
- `ownerPreviewReviewComment = null`
- `resolutionMode = PUBLISHED` when a published version is surfaced
- `headlineVersion` equals `publishedVersion`

Important constraints from Java:

- Do not copy earlier resolve/list SQL blindly. Java detail uses
  `SkillSlugResolutionService.resolve(..., Preference.CURRENT_USER)`, which for anonymous callers
  selects a non-hidden skill with `latest_version_id IS NOT NULL`.
- Java visibility then checks `VisibilityChecker.canAccess`. Anonymous callers can access only
  `PUBLIC` skills with `latest_version_id IS NOT NULL` and `hidden = false`.
- Java lifecycle projection resolves the published version from `latest_version_id` if it points to
  a `PUBLISHED` version, otherwise it falls back to the newest `PUBLISHED` version by
  `published_at`, `created_at`, then `id`.
- Hidden, private, namespace-only, missing namespace, missing skill, and no-public-version cases
  must be checked against Java in the live gate before result is marked passed.

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_detail.py`
- `server-python/tests/test_skill_detail_repository.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-detail-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Object storage integration code
- Auth/session/CSRF bridge code

## Route Ownership And Vite Proxy

Add exact regex proxy entries before the more specific version/files routes and before the generic
`/api` fallback:

```ts
      '^/api/v1/skills/[^/]+/[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
```

These patterns must not capture:

- `/api/v1/skills`
- `/api/web/skills`
- `/api/v1|web/skills/{namespace}/{slug}/labels`
- `/api/v1|web/skills/{namespace}/{slug}/resolve`
- `/api/v1|web/skills/{namespace}/{slug}/versions`
- `/api/v1|web/skills/{namespace}/{slug}/versions/**`
- `/api/v1|web/skills/{namespace}/{slug}/tags/**`
- `/api/v1|web/skills/{namespace}/{slug}/download`

---

## Task 1: Response Builder Tests

**Files:**

- Create: `server-python/tests/test_skill_detail_repository.py`
- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Write failing response mapping tests**

Add tests for Java-compatible field names, decimal preservation, labels, lifecycle projections, and
anonymous public capability flags.

```python
from decimal import Decimal

from app.api.skills import build_skill_detail_response


def test_build_skill_detail_response_maps_java_fields() -> None:
    row = {
        "id": 31,
        "slug": "demo-skill",
        "display_name": "Demo Skill",
        "owner_id": "owner-1",
        "owner_display_name": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 7,
        "star_count": 3,
        "subscription_count": 2,
        "rating_avg": Decimal("4.50"),
        "rating_count": 4,
        "hidden": False,
        "namespace": "global",
        "published_version_id": 41,
        "published_version": "1.2.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
    }
    labels = [
        {"slug": "featured", "type": "RECOMMENDED", "displayName": "Featured"},
    ]

    assert build_skill_detail_response(row, labels) == {
        "id": 31,
        "slug": "demo-skill",
        "displayName": "Demo Skill",
        "ownerId": "owner-1",
        "ownerDisplayName": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "downloadCount": 7,
        "starCount": 3,
        "subscriptionCount": 2,
        "ratingAvg": 4.5,
        "ratingCount": 4,
        "hidden": False,
        "namespace": "global",
        "labels": labels,
        "canManageLifecycle": False,
        "canSubmitPromotion": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": "PUBLISHED",
    }
```

- [ ] **Step 2: Run test and confirm RED**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail_repository.py -v
```

Expected: FAIL because `build_skill_detail_response` does not exist.

- [ ] **Step 3: Implement minimal response builder**

Add helper functions in `server-python/app/api/skills.py`:

```python
def to_lifecycle_version(row: dict[str, Any]) -> dict[str, object] | None:
    if row["published_version_id"] is None:
        return None
    return {
        "id": int(row["published_version_id"]),
        "version": str(row["published_version"]),
        "status": str(row["published_version_status"]),
    }


def build_skill_detail_response(
    row: dict[str, Any],
    labels: list[dict[str, object]],
) -> dict[str, object]:
    published_version = to_lifecycle_version(row)
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "ownerId": str(row["owner_id"]),
        "ownerDisplayName": row["owner_display_name"],
        "summary": row["summary"],
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "downloadCount": int(row["download_count"]),
        "starCount": int(row["star_count"]),
        "subscriptionCount": int(row["subscription_count"]),
        "ratingAvg": float(row["rating_avg"]),
        "ratingCount": int(row["rating_count"]),
        "hidden": bool(row["hidden"]),
        "namespace": str(row["namespace"]),
        "labels": labels,
        "canManageLifecycle": False,
        "canSubmitPromotion": False,
        "canInteract": published_version is None or published_version["status"] == "PUBLISHED",
        "canReport": True,
        "headlineVersion": published_version,
        "publishedVersion": published_version,
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": str(row["resolution_mode"]),
    }
```

- [ ] **Step 4: Run test and confirm GREEN**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail_repository.py -v
```

Expected: PASS.

## Task 2: Route Tests

**Files:**

- Create: `server-python/tests/test_skill_detail.py`
- Modify: `server-python/app/api/skills.py`

- [ ] **Step 1: Write failing route tests**

Add tests for both aliases, envelope, request id propagation, and parameter forwarding.

```python
from fastapi.testclient import TestClient

from app.main import create_app


def detail_response() -> dict[str, object]:
    return {
        "id": 31,
        "slug": "demo-skill",
        "displayName": "Demo Skill",
        "ownerId": "owner-1",
        "ownerDisplayName": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "downloadCount": 7,
        "starCount": 3,
        "subscriptionCount": 2,
        "ratingAvg": 4.5,
        "ratingCount": 4,
        "hidden": False,
        "namespace": "global",
        "labels": [],
        "canManageLifecycle": False,
        "canSubmitPromotion": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": "PUBLISHED",
    }


def test_skill_detail_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug: detail_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo-skill",
        headers={"X-Request-Id": "detail-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "detail-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "?瑕???"
    assert response.json()["requestId"] == "detail-test"
    assert response.json()["data"] == detail_response()


def test_skill_detail_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_detail_reader = lambda namespace, slug: detail_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo-skill")

    assert response.status_code == 200
    assert response.json()["data"] == detail_response()


def test_skill_detail_route_forwards_params_to_reader() -> None:
    seen: list[tuple[str, str]] = []
    app = create_app()

    def reader(namespace: str, slug: str) -> dict[str, object]:
        seen.append((namespace, slug))
        return detail_response()

    app.state.skill_detail_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/team-a/demo-skill")

    assert response.status_code == 200
    assert seen == [("team-a", "demo-skill")]
```

- [ ] **Step 2: Run route tests and confirm RED**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail.py -v
```

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Add route handlers**

Add the detail route below the helper functions and before narrower nested routes are affected:

```python
@router.get("/api/v1/skills/{namespace}/{slug}")
@router.get("/api/web/skills/{namespace}/{slug}")
async def get_skill_detail(
    namespace: str,
    slug: str,
    request: Request,
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug))
        else:
            data = await read_skill_detail(request.app.state.db_engine, namespace, slug)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("?瑕???", data, request)
```

- [ ] **Step 4: Run route tests and confirm GREEN**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail.py -v
```

Expected: PASS.

## Task 3: PostgreSQL Reader

**Files:**

- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/tests/test_skill_detail_repository.py`

- [ ] **Step 1: Add repository-level tests for labels and no-published projection**

Extend `tests/test_skill_detail_repository.py` with builder tests for:

- labels sorted by Java query output
- `headlineVersion = null`, `publishedVersion = null`, `resolutionMode = NONE` when Java returns no
  published projection for the selected public skill
- `ownerDisplayName = null` when owner display name is blank or missing

- [ ] **Step 2: Implement DB reader**

Add `read_skill_detail(engine, namespace, slug)` using raw SQL:

1. Select the anonymous visible skill:
   - namespace slug matches
   - namespace status is not missing
   - skill slug matches
   - skill status is `ACTIVE`
   - `hidden = false`
   - `visibility = 'PUBLIC'`
   - `latest_version_id IS NOT NULL`
   - order by `s.id ASC`
   - limit 1
2. Reject archived namespaces for anonymous viewers with status parity against Java.
3. Resolve published version:
   - prefer `skill.latest_version_id` when that version is `PUBLISHED`
   - otherwise choose newest `PUBLISHED` by `published_at`, `created_at`, `id`
4. Load labels by joining:
   - `skill_label`
   - `label_definition`
   - `label_translation`
5. Resolve label display name:
   - prefer `en`
   - fallback to label slug

The reader returns `build_skill_detail_response(row, labels)`.

- [ ] **Step 3: Run focused Python tests**

Run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail.py tests/test_skill_detail_repository.py -v
```

Expected: PASS.

## Task 4: Vite Proxy Ownership

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [ ] **Step 1: Add proxy matching tests**

Extend `web/vite.config.test.ts` to assert:

- `/api/v1/skills/global/demo` routes to Python
- `/api/web/skills/global/demo` routes to Python
- `/api/v1/skills` falls through to Java
- `/api/web/skills` falls through to Java
- nested routes already owned by Python still route to Python
- nested routes owned by Java still route to Java

- [ ] **Step 2: Run proxy tests and confirm RED**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: FAIL because detail proxy entries do not exist.

- [ ] **Step 3: Add proxy entries**

Add exact regex entries in `web/vite.config.ts` before `/api` fallback:

```ts
      '^/api/v1/skills/[^/]+/[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
```

- [ ] **Step 4: Run proxy tests and confirm GREEN**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: PASS.

- [ ] **Step 5: Update docs**

Update:

- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`

Mark the detail routes as Python-owned after implementation and link the result document after
verification.

## Task 5: Windows Live Contract Gate

**Files:**

- Modify: `scripts/dev-hybrid.ps1`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Create: `docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md`
- Modify: `docs/backend-python-migration/windows-live-verification.md` if new Windows-specific
  troubleshooting is learned

- [ ] **Step 1: Add `verify-detail-smoke` action**

Extend `scripts/dev-hybrid.ps1` with a new action that:

- starts Java, Python, Vite, PostgreSQL, Redis, MinIO, and scanner
- creates deterministic PostgreSQL fixture data
- compares Java direct, Python direct, Vite `/api/v1`, and Vite `/api/web`
- runs Playwright smoke
- stops the hybrid stack

Fixture should include:

- `global` namespace
- owner user with display name
- public active skill with `latest_version_id`
- latest published version `1.2.0`
- older published version `1.0.0`
- newer draft version `2.0.0-draft` that anonymous users must not see as owner preview
- at least one attached label with `en` translation
- hidden skill with same shape for negative status comparison
- public active skill with no `latest_version_id` for negative status comparison

- [ ] **Step 2: Run live gate**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-detail-smoke
```

Expected:

- Java and Python stable `code`, `msg`, and `data` match for public detail
- Python and both Vite proxy aliases match
- hidden/no-public-version negative statuses match Java
- Playwright smoke passes

- [ ] **Step 3: Run final verification**

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

- Python tests pass
- Vite proxy tests pass
- `git diff --check` has no whitespace errors
- `git diff --name-only -- server` is empty

- [ ] **Step 4: Write result document**

Create `docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md` with:

- routes changed
- owner before/after
- implementation summary
- tests
- live Java/Python/proxy comparison summary
- negative cases
- boundary check
- risks and follow-up

- [ ] **Step 5: Commit and push**

Commit and push only after the result document is complete:

```powershell
git add server-python/app/api/skills.py `
  server-python/tests/test_skill_detail.py `
  server-python/tests/test_skill_detail_repository.py `
  server-python/tests/test_hybrid_makefile.py `
  web/vite.config.ts `
  web/vite.config.test.ts `
  scripts/dev-hybrid.ps1 `
  docs/backend-python-migration/route-registry.md `
  docs/backend-python-migration/migration-sequence-plan.md `
  docs/backend-python-migration/plans/2026-06-07-public-skill-detail-api.md `
  docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md
git commit -m "feat(skills): migrate public skill detail"
git push origin dev
```

## Acceptance Criteria

- `GET /api/v1/skills/{namespace}/{slug}` and `/api/web/...` are Python-owned in Vite dev.
- Public anonymous Java/Python/proxy responses match for stable fields.
- Nested routes keep their existing Java/Python ownership.
- Hidden/no-public-version/archived negative behavior is compared against Java.
- `cd server-python; uv run pytest` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- `scripts\dev-hybrid.ps1 verify-detail-smoke` passes on Windows.
- `git diff --name-only -- server` is empty.
- Result document is written before commit.
