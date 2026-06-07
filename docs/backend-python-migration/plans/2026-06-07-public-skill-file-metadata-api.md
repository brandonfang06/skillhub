# Public Skill File Metadata API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public read-only skill file metadata API to FastAPI while Java and Python
continue to coexist.

**Architecture:** Python will own only the anonymous/public GET file metadata list aliases for a concrete
version or tag. The implementation extends the existing `skills` API module, reuses anonymous public skill
lookup from previous milestones, returns Java-compatible list of `SkillFileResponse` structures, and leaves
actual file content and download routes on Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, live
Java/Python/DB contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/files` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/files` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | java | python |

This milestone does not migrate:

- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/file` (content)
- `GET /api/v1|web/skills/{namespace}/{slug}/tags/{tagName}/file` (content)
- `GET /api/v1|web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1|web/skills/{namespace}/{slug}/tags/{tagName}/download`
- `GET /api/v1|web/skills/{namespace}/{slug}/download` (latest download)

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java` (lines 206-262)
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillQueryService.java` (lines 382-410)
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/SkillFile.java`

Observed Java contract:

- Controller returns `ok("response.success.read", List<SkillFileResponse>)`.
- Localized Java default `msg` is `获取成功`.
- Response fields for each file in the array:
  - `id`
  - `filePath`
  - `fileSize`
  - `contentType`
  - `sha256`
- Results are ordered by `file_path ASC`.
- Anonymous callers may inspect files for `PUBLISHED` versions only.

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
- `server-python/tests/test_skill_file_metadata.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-file-metadata-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-file-metadata-api.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- MinIO/S3/local object storage integrations

## Route Ownership And Vite Proxy

Add these exact regex proxy entries before the generic `/api` fallback:

```ts
      '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
```

Ensure `/file` and `/download` routes are NOT captured by these regex patterns and remain on Java.

---

## Task 1: Route Tests

**Files:**
- Create: `server-python/tests/test_skill_file_metadata.py`

- [x] **Step 1: Write failing route tests**

Add tests for both aliases, tags, versions, and Request ID propagation:

```python
from fastapi.testclient import TestClient
from app.main import create_app

def files_response() -> list[dict[str, object]]:
    return [
        {
            "id": 21,
            "filePath": "SKILL.md",
            "fileSize": 1024,
            "contentType": "text/markdown",
            "sha256": "hash-skill-md"
        },
        {
            "id": 22,
            "filePath": "app.py",
            "fileSize": 2048,
            "contentType": "text/x-python",
            "sha256": "hash-app-py"
        }
    ]

def test_skill_version_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_files_reader = lambda namespace, slug, version: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0/files",
        headers={"X-Request-Id": "files-version-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-version-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-version-test"
    assert response.json()["data"] == files_response()

def test_skill_tag_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_tag_files_reader = lambda namespace, slug, tag: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/latest/files",
        headers={"X-Request-Id": "files-tag-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-tag-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-tag-test"
    assert response.json()["data"] == files_response()
```

- [x] **Step 2: Run tests and confirm RED**

Run:
```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_file_metadata.py -v
```
Expected: FAIL with `404 Not Found` for both routes.

---

## Task 2: Database Readers Implementation

**Files:**
- Modify: `server-python/app/api/skills.py`

- [x] **Step 1: Write database query logic**

Add `read_skill_version_files` and `read_skill_tag_files` in `server-python/app/api/skills.py` using raw SQL queries with visibility and PUBLISHED status verification.

Implementation of `read_skill_version_files`:
```python
async def read_skill_version_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_id = (
            await connection.execute(
                text(
                    """
                    SELECT s.id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

        if skill_id is None:
            raise SkillResolveError("error.skill.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_id, "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")

        version_id = version_row["id"]

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]
```

Implementation of `read_skill_tag_files`:
```python
async def read_skill_tag_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        skill_id = skill_row["id"]

        if tag_name.lower() == "latest":
            version_id = skill_row["latest_version_id"]
        else:
            version_id = (
                await connection.execute(
                    text(
                        """
                        SELECT version_id
                        FROM skill_tag
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        LIMIT 1
                        """
                    ),
                    {"skill_id": skill_id, "tag_name": tag_name},
                )
            ).scalar_one_or_none()

            if version_id is None:
                raise SkillResolveError("error.skill.tag.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE id = :version_id
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                    ),
                {"version_id": version_id},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.tag.version.notFound")

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]
```

- [x] **Step 2: Commit after reader logic is in**

```bash
git add server-python/app/api/skills.py
git commit -m "feat(skills): implement DB reader logic for public skill file metadata"
```

---

## Task 3: Minimal FastAPI Implementation

**Files:**
- Modify: `server-python/app/api/skills.py`

- [x] **Step 1: Implement route handlers**

Add route handlers for versions files and tags files:
```python
@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/files")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/files")
async def list_skill_version_files(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
) -> list[dict[str, object]]:
    reader = getattr(request.app.state, "skill_version_files_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version))
        else:
            data = await read_skill_version_files(request.app.state.db_engine, namespace, slug, version)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/files")
async def list_skill_tag_files(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
) -> list[dict[str, object]]:
    reader = getattr(request.app.state, "skill_tag_files_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, tagName))
        else:
            data = await read_skill_tag_files(request.app.state.db_engine, namespace, slug, tagName)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)
```

- [x] **Step 2: Run tests and confirm GREEN**

Run:
```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_file_metadata.py -v
```
Expected: PASS.

- [x] **Step 3: Commit**

```bash
git add server-python/app/api/skills.py server-python/tests/test_skill_file_metadata.py
git commit -m "feat(skills): add routes and pytest cases for public skill file metadata"
```

---

## Task 4: Vite Proxy And Registry

**Files:**
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [x] **Step 1: Write proxy test assertions**

Add tests to `web/vite.config.test.ts`:
```ts
  it('routes skill files list aliases to Python without taking over file content or download routes', () => {
    const proxy = config.server?.proxy as Record<string, ProxyTarget>
    const keys = Object.keys(proxy)
    const v1SkillVersionFiles = '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const webSkillVersionFiles = '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$'
    const v1SkillTagFiles = '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$'
    const webSkillTagFiles = '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$'

    expect(proxy[v1SkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillVersionFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[v1SkillTagFiles]?.target).toBe('http://localhost:8081')
    expect(proxy[webSkillTagFiles]?.target).toBe('http://localhost:8081')

    // file and download should NOT route to Python
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/file$']?.target).toBeUndefined()
    expect(proxy['^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()
    expect(proxy['^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/download$']?.target).toBeUndefined()

    expect(keys.indexOf(v1SkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillVersionFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(v1SkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
    expect(keys.indexOf(webSkillTagFiles)).toBeLessThan(keys.indexOf('/api'))
  })
```

- [x] **Step 2: Run proxy tests and confirm RED**

Run:
```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```
Expected: FAIL due to missing files proxy entries.

- [x] **Step 3: Modify `web/vite.config.ts`**

Add the entries in `web/vite.config.ts` proxy mapping:
```ts
      '^/api/v1/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/versions/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/v1/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
      '^/api/web/skills/[^/]+/[^/]+/tags/[^/]+/files$': {
        target: 'http://localhost:8081',
        changeOrigin: true,
      },
```

- [x] **Step 4: Run proxy tests and confirm GREEN**

Run:
```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```
Expected: PASS.

- [x] **Step 5: Update Route Registry and Sequence Plan**

Update `docs/backend-python-migration/route-registry.md` to reflect `python` ownership for:
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files`

Update `docs/backend-python-migration/migration-sequence-plan.md` to mark this milestone as completed/active.

- [x] **Step 6: Commit**

```bash
git add web/vite.config.ts web/vite.config.test.ts docs/backend-python-migration/route-registry.md docs/backend-python-migration/migration-sequence-plan.md
git commit -m "chore(config): update vite proxy and route registry for files metadata"
```

---

## Task 5: Live Contract Verification

- [x] **Step 1: Start the hybrid stack**

Run `make dev-all` or check that the stack is running.

- [x] **Step 2: Compare Java and Python responses**

Compare the response for `/api/v1/skills/global/demo/versions/1.0.0/files` (or another valid skill version in local db) between:
- Direct Java (`http://localhost:8080`)
- Direct Python (`http://localhost:8081`)
- Vite Proxy (`http://localhost:3000`)

Ensure fields `id`, `filePath`, `fileSize`, `contentType`, `sha256` are identical in values and ordering.

- [x] **Step 3: Run smoke E2E**

```powershell
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts
```

- [x] **Step 4: Document results**

Create `docs/backend-python-migration/results/2026-06-07-public-skill-file-metadata-api.md` detailing the verification outcome.

- [x] **Step 5: Run final validation check**

Run:
```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
cd ..
git diff --name-only -- server
git diff --check
```
Ensure no Java files under `server/` were modified, and all checks pass.
