# Public Skill Resolve API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public read-only skill version resolve API to FastAPI while Java and Python
continue to coexist.

**Architecture:** Python will own only the anonymous/public GET resolve aliases. The implementation
adds a focused `skills` API module, reads PostgreSQL using the existing async engine, mirrors Java
selector rules for published public versions, and returns the same `ResolveVersionResponse` envelope
without implementing file download, storage access, or download counters.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vitest, Vite dev proxy, live
Java/Python/DB contract comparison.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | java | python |

This milestone does not migrate:

- Any `/download` route.
- Any file content or file streaming route.
- Download counters, rate limiting, object storage, S3, MinIO, or local file bundle access.
- Authenticated owner preview, namespace-only/private access, hidden preview, or SUPER_ADMIN bypass.
- Any mutating skill lifecycle, tag, label, social, or governance endpoint.

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/ResolveVersionResponse.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillQueryService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillSlugResolutionService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`

Observed Java contract:

- Controller returns `ok("response.success.read", ResolveVersionResponse)`.
- Localized Java default `msg` is `获取成功`.
- DTO fields are:
  - `skillId`
  - `namespace`
  - `slug`
  - `version`
  - `versionId`
  - `fingerprint`
  - `matched`
  - `downloadUrl`
- Query params:
  - `version`: exact published version selector.
  - `tag`: tag selector; `latest` resolves `skill.latest_version_id`.
  - `hash`: compares against computed version fingerprint.
- `version` and `tag` together return a bad-request error in Java. Python must reject the same
  invalid selector combination instead of silently choosing one.
- When only `hash` is provided, Java returns the matching published version if found; otherwise it
  returns latest and sets `matched=false`.
- When no selector is provided, Java resolves latest.
- Fingerprint is `sha256:` plus a SHA-256 digest over sorted file lines:
  `file_path + ":" + sha256 + "\n"`.
- `downloadUrl` is a Java-compatible relative path:
  `/api/v1/skills/{encodedNamespace}/{encodedSlug}/versions/{encodedVersion}/download`.

Because Python has no auth/session bridge yet, this milestone implements anonymous public behavior
only. Anonymous public access requires:

- a matching namespace slug
- `namespace.status = 'ACTIVE'`
- a matching skill slug
- `skill.status = 'ACTIVE'`
- `skill.latest_version_id IS NOT NULL`
- `skill.hidden = false`
- `skill.visibility = 'PUBLIC'`
- returned versions must have `status = 'PUBLISHED'`

## Allowed Files

- `server-python/app/api/skills.py`
- `server-python/app/main.py`
- `server-python/tests/test_skill_resolve.py`
- `server-python/tests/test_skill_resolve_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-resolve-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-resolve-api.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Auth/session/OAuth/API token code
- Download/storage/rate-limit implementation

## Route Ownership And Vite Proxy

Add these exact regex proxy entries before the generic `/api` fallback:

```ts
'^/api/v1/skills/[^/]+/[^/]+/resolve$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
'^/api/web/skills/[^/]+/[^/]+/resolve$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
```

The route registry must add:

```markdown
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | python | Public anonymous version selector resolution. Download remains Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | python | Frontend alias for public anonymous version selector resolution. Download remains Java-owned. |
```

## Task 1: Route Tests

**Files:**

- Create: `server-python/tests/test_skill_resolve.py`

- [ ] **Step 1: Write failing route tests**

Add tests that exercise both aliases, request id propagation, and selector forwarding:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_skill_resolve_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_resolve_reader = lambda namespace, slug, version, tag, hash_value: {
        "skillId": 1,
        "namespace": namespace,
        "slug": slug,
        "version": tag or "1.2.0",
        "versionId": 20,
        "fingerprint": "sha256:abc",
        "matched": None,
        "downloadUrl": "/api/v1/skills/global/demo/versions/1.2.0/download",
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/resolve",
        params={"tag": "latest"},
        headers={"X-Request-Id": "resolve-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "resolve-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "resolve-test"
    assert response.json()["data"]["namespace"] == "global"
    assert response.json()["data"]["slug"] == "demo"
    assert response.json()["data"]["downloadUrl"] == "/api/v1/skills/global/demo/versions/1.2.0/download"


def test_skill_resolve_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_resolve_reader = lambda namespace, slug, version, tag, hash_value: {
        "skillId": 2,
        "namespace": namespace,
        "slug": slug,
        "version": "1.0.0",
        "versionId": 10,
        "fingerprint": "sha256:def",
        "matched": True,
        "downloadUrl": "/api/v1/skills/global/demo/versions/1.0.0/download",
    }

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/resolve", params={"hash": "sha256:def"})

    assert response.status_code == 200
    assert response.json()["data"]["matched"] is True
    assert response.json()["data"]["version"] == "1.0.0"
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_resolve.py -v
```

Expected failure: `404 Not Found` for both resolve routes.

## Task 2: Pure Resolve Helper Tests

**Files:**

- Create: `server-python/tests/test_skill_resolve_repository.py`
- Create: `server-python/app/api/skills.py`

- [ ] **Step 1: Write failing pure helper tests**

Add tests for selector behavior and fingerprint/download URL formatting:

```python
import pytest

from app.api.skills import (
    SkillResolveError,
    build_resolve_response,
    compute_version_fingerprint,
    resolve_version_row,
)


def test_compute_version_fingerprint_sorts_files_by_path() -> None:
    files = [
        {"file_path": "z.txt", "sha256": "hash-z"},
        {"file_path": "a.txt", "sha256": "hash-a"},
    ]

    assert compute_version_fingerprint(files) == (
        "sha256:3965fc21b1d1b8e33b27b228e6a5377ad9786196cc8f72b1fc011fa34cf6a747"
    )


def test_resolve_version_row_uses_latest_without_selector() -> None:
    latest = {"id": 20, "version": "1.2.0"}

    assert resolve_version_row(
        versions=[{"id": 10, "version": "1.0.0"}, latest],
        latest_version_id=20,
        tags={},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version=None,
        tag=None,
        hash_value=None,
    ) == (latest, None)


def test_resolve_version_row_rejects_version_and_tag_conflict() -> None:
    with pytest.raises(SkillResolveError, match="error.skill.resolve.versionTag.conflict"):
        resolve_version_row(
            versions=[],
            latest_version_id=None,
            tags={},
            fingerprints={},
            version="1.0.0",
            tag="latest",
            hash_value=None,
        )


def test_build_resolve_response_encodes_download_url_path_segments() -> None:
    assert build_resolve_response(
        skill_id=1,
        namespace="global",
        slug="demo skill",
        version_row={"id": 11, "version": "1.0.0 beta"},
        fingerprint="sha256:abc",
        matched=None,
    )["downloadUrl"] == "/api/v1/skills/global/demo%20skill/versions/1.0.0%20beta/download"
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_resolve_repository.py -v
```

Expected failure: missing `app.api.skills`.

## Task 3: Minimal FastAPI Implementation

**Files:**

- Create: `server-python/app/api/skills.py`
- Modify: `server-python/app/main.py`

- [ ] **Step 1: Implement route and helper behavior**

Implementation requirements:

- Add route aliases:
  - `/api/v1/skills/{namespace}/{slug}/resolve`
  - `/api/web/skills/{namespace}/{slug}/resolve`
- Route handler remains thin: bind path/query params, call reader, return `ok("获取成功", data, request)`.
- Support test injection via `app.state.skill_resolve_reader`.
- Add `read_skill_resolve(engine, namespace, slug, version, tag, hash_value)`.
- Query an anonymous public skill using namespace and skill visibility/status constraints.
- Load published versions for the skill.
- Load tags for the skill.
- Load files for all published versions needed to compute fingerprints.
- Return Java-compatible data fields exactly.

- [ ] **Step 2: Run focused Python tests and confirm GREEN**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_resolve.py tests/test_skill_resolve_repository.py -v
```

Expected: tests pass.

## Task 4: Vite Proxy And Registry

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`

- [ ] **Step 1: Add failing Vite proxy test expectations**

Add expectations that `^/api/v1/skills/[^/]+/[^/]+/resolve$` and
`^/api/web/skills/[^/]+/[^/]+/resolve$` target Python before `/api`, without taking ownership of
the broader `/api/v1/skills` or `/api/web/skills` prefixes.

- [ ] **Step 2: Run frontend config test and confirm RED**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected failure: missing resolve proxy entries.

- [ ] **Step 3: Add proxy entries**

Add the two route ownership entries before `/api`.

- [ ] **Step 4: Update route registry**

Add both resolve routes as Python-owned.

- [ ] **Step 5: Run frontend config test and confirm GREEN**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: pass.

## Task 5: Live Contract Verification

**Files:**

- Create: `docs/backend-python-migration/results/2026-06-07-public-skill-resolve-api.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [ ] **Step 1: Start the hybrid stack**

On Windows Codex sandbox:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

- [ ] **Step 2: Create or reuse a public fixture**

Use local Docker PostgreSQL only. Fixture must have:

- an active public namespace
- an active public, non-hidden skill
- latest version `1.2.0`, status `PUBLISHED`
- older version `1.0.0`, status `PUBLISHED`
- tag `stable` pointing at `1.0.0`
- at least one `skill_file` row per version so fingerprint comparison is meaningful

- [ ] **Step 3: Compare Java, Python, and Vite proxy**

Stable comparison fields:

- `code`
- `msg`
- `data.skillId`
- `data.namespace`
- `data.slug`
- `data.version`
- `data.versionId`
- `data.fingerprint`
- `data.matched`
- `data.downloadUrl`

Scenarios:

- no selector resolves latest
- `tag=latest` resolves latest
- `version=1.0.0` resolves exact version
- `tag=stable` resolves tagged version
- matching `hash` resolves matched version and sets `matched=true`
- non-matching `hash` resolves latest and sets `matched=false`
- `version=1.0.0&tag=latest` returns a bad request from both Java and Python

Ignore volatile fields:

- `timestamp`
- `requestId`

- [ ] **Step 4: Run smoke E2E**

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
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

- [ ] **Step 6: Write result document**

Record:

- routes changed
- owner before/after
- files changed
- unit tests
- Vite proxy tests
- live comparison scenarios
- E2E smoke result
- risks and follow-up

## Acceptance Criteria

- Both resolve GET routes are Python-owned in Vite dev proxy.
- Both aliases return the Java-compatible envelope and `ResolveVersionResponse` fields.
- Python implements anonymous public behavior only and documents auth-specific behavior as deferred.
- Java/Python/proxy stable contract comparison passes for latest/version/tag/hash/conflict scenarios.
- Frontend smoke E2E passes.
- `git diff --name-only -- server` returns empty output.
- Result document is written before commit.
- Milestone is committed and pushed to `dev`.

## Risks

- Java returns localized error envelopes for invalid selectors through its global exception handler.
  Python must match status and stable error intent; exact localized failure body can be documented if
  framework-level exception shape differs.
- Python currently has no auth/session bridge. Owner preview, namespace-only access, private access,
  hidden preview, archived namespace member access, and SUPER_ADMIN behavior remain Java-owned/deferred.
- Download URLs are returned for compatibility, but download execution remains Java-owned until the
  storage/download bridge is explicitly planned.
