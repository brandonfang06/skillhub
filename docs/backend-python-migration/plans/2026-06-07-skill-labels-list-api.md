# Skill Labels List API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public read-only skill labels list API to FastAPI while Java and Python
continue to coexist.

**Architecture:** Python will own only the GET list routes for skill labels. The implementation
reuses the existing Python PostgreSQL engine and label localization helpers, resolves anonymous
public skill visibility from PostgreSQL, and leaves all skill-label mutations and auth-specific
preview behavior on Java.

**Tech Stack:** FastAPI, SQLAlchemy async engine, asyncpg, pytest, Vite dev proxy.

---

## Milestone Announcement

This milestone migrates:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | java | python |

This milestone does not migrate:

- `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- Any admin label endpoint
- Any auth/session/RBAC bridge

## Java Reference Behavior

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLabelController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLabelAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLabelDto.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/VisibilityChecker.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillSlugResolutionService.java`

Observed Java contract:

- Controller returns `ok("response.success.read", List<SkillLabelDto>)`.
- Localized Java default `msg` is `获取成功`.
- DTO fields are:
  - `slug`
  - `type`
  - `displayName`
- DTO order is `type ASC`, then `slug ASC`.
- Skill slug resolution prefers:
  - current user's own skill when `userId` exists
  - otherwise a published, non-hidden skill
- Because Python has no auth bridge yet, this milestone implements anonymous public behavior only.
- Anonymous public access requires:
  - a matching namespace slug
  - a matching skill slug
  - `skill.latest_version_id IS NOT NULL`
  - `skill.hidden = false`
  - `skill.visibility = 'PUBLIC'`

## Allowed Files

- `server-python/app/api/labels.py`
- `server-python/app/main.py` only if a new router split becomes necessary
- `server-python/tests/test_labels.py`
- `server-python/tests/test_label_repository.py`
- `server-python/tests/test_hybrid_makefile.py` only if live verification script changes
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-skill-labels-list-api.md`
- `docs/backend-python-migration/results/2026-06-07-skill-labels-list-api.md`

## Forbidden Files

- Any path under `server/`
- `web/src/api/generated/schema.d.ts`
- Java migrations, Java tests, Java resources
- Auth/session/OAuth code

## Route Ownership And Vite Proxy

Add these regex proxy entries before the generic `/api` fallback:

```ts
'^/api/v1/skills/[^/]+/[^/]+/labels$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
'^/api/web/skills/[^/]+/[^/]+/labels$': {
  target: 'http://localhost:8081',
  changeOrigin: true,
},
```

The route registry must add:

```markdown
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | python | Public anonymous skill labels list. Mutations remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | python | Frontend alias for public anonymous skill labels list. Mutations remain Java-owned. |
```

## Task 1: Route Tests

**Files:**

- Modify: `server-python/tests/test_labels.py`

- [ ] **Step 1: Write failing route tests**

Add tests that exercise both aliases and the Java-compatible envelope:

```python
def test_skill_labels_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_label_reader = lambda namespace, slug, locale: [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"}
    ]

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/labels",
        headers={"X-Request-Id": "skill-labels-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "skill-labels-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "skill-labels-test"
    assert response.json()["data"] == [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"}
    ]


def test_skill_labels_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_label_reader = lambda namespace, slug, locale: [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/labels")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_labels.py::test_skill_labels_v1_route_returns_envelope tests/test_labels.py::test_skill_labels_web_alias_returns_same_contract -v
```

Expected failure: `404 Not Found` for both skill labels routes.

## Task 2: Repository Helper Tests

**Files:**

- Modify: `server-python/tests/test_label_repository.py`
- Modify: `server-python/app/api/labels.py`

- [ ] **Step 1: Write failing pure helper tests**

Add helper tests that lock Java's sorting and anonymous visibility assumptions without needing a
live database:

```python
from app.api.labels import build_skill_label_response


def test_build_skill_label_response_sorts_by_type_then_slug_and_localizes() -> None:
    labels = [
        {"id": 3, "slug": "team", "type": "RECOMMENDED"},
        {"id": 1, "slug": "verified", "type": "PRIVILEGED"},
        {"id": 2, "slug": "official", "type": "PRIVILEGED"},
    ]
    translations = [
        {"label_id": 1, "locale": "en", "display_name": "Verified"},
        {"label_id": 2, "locale": "en", "display_name": "Official"},
        {"label_id": 3, "locale": "en", "display_name": "Team"},
    ]

    assert build_skill_label_response(labels, translations, "en") == [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"},
        {"slug": "verified", "type": "PRIVILEGED", "displayName": "Verified"},
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"},
    ]
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_label_repository.py::test_build_skill_label_response_sorts_by_type_then_slug_and_localizes -v
```

Expected failure: `ImportError` or missing `build_skill_label_response`.

## Task 3: Minimal FastAPI Implementation

**Files:**

- Modify: `server-python/app/api/labels.py`

- [ ] **Step 1: Add helper and route implementation**

Implementation shape:

```python
def build_skill_label_response(
    labels: list[LabelRow],
    translations: list[TranslationRow],
    locale: str | None,
) -> list[dict[str, str]]:
    translations_by_label: dict[int, list[TranslationRow]] = defaultdict(list)
    for translation in translations:
        translations_by_label[int(translation["label_id"])].append(translation)

    labels.sort(key=lambda label: (str(label["type"]), str(label["slug"])))

    return [
        {
            "slug": str(label["slug"]),
            "type": str(label["type"]),
            "displayName": resolve_display_name(
                str(label["slug"]),
                translations_by_label[int(label["id"])],
                locale,
            ),
        }
        for label in labels
    ]
```

The DB query must:

- Resolve namespace by `namespace.slug`.
- Resolve anonymous public skill by `skill.slug`, `skill.hidden = false`,
  `skill.latest_version_id IS NOT NULL`, and `skill.visibility = 'PUBLIC'`.
- Join `skill_label` to `label_definition`.
- Load translations for returned label ids.
- Return an empty list when the skill exists and has no labels.

- [ ] **Step 2: Run focused tests and confirm GREEN**

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_labels.py tests/test_label_repository.py -v
```

Expected: tests pass.

## Task 4: Vite Proxy And Registry

**Files:**

- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `docs/backend-python-migration/route-registry.md`

- [ ] **Step 1: Add failing Vite proxy test expectations**

Add expectations that `^/api/v1/skills/[^/]+/[^/]+/labels$` and
`^/api/web/skills/[^/]+/[^/]+/labels$` target Python before `/api`.

- [ ] **Step 2: Run frontend config test and confirm RED**

```powershell
cd web
corepack pnpm vitest run vite.config.test.ts
```

Expected failure: missing proxy entries.

- [ ] **Step 3: Add proxy entries**

Add the two route ownership entries before `/api`.

- [ ] **Step 4: Update route registry**

Add the two GET routes as Python-owned.

- [ ] **Step 5: Run frontend config test and confirm GREEN**

```powershell
cd web
corepack pnpm vitest run vite.config.test.ts
```

Expected: pass.

## Task 5: Live Contract Verification

**Files:**

- Create: `docs/backend-python-migration/results/2026-06-07-skill-labels-list-api.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`

- [ ] **Step 1: Start or reuse the hybrid stack**

On Windows Codex sandbox:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

- [ ] **Step 2: Compare Java, Python, and proxy**

Use a known public skill coordinate from local bootstrap data. If no public skill exists locally,
record that fixture gap and use route-level/proxy verification only until a fixture is available.

Stable comparison fields:

- `code`
- `msg`
- `data`

Ignore:

- `timestamp`
- `requestId`

- [ ] **Step 3: Run smoke E2E**

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

- [ ] **Step 4: Run final checks**

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
- `git diff --name-only -- server` returns empty output.
- `git diff --check` has no whitespace errors.

- [ ] **Step 5: Write result document**

Record:

- Routes changed.
- Owner before/after.
- Unit tests.
- Vite proxy tests.
- Live comparison results.
- E2E smoke result.
- Risks and follow-up.

## Acceptance Criteria

- Both skill labels GET routes are Python-owned in Vite dev proxy.
- Both aliases return the Java-compatible envelope and `SkillLabelDto` list.
- Python implements anonymous/public visibility only and documents auth-specific behavior as
  deferred.
- Java/Python/proxy stable contract comparison passes when a local public fixture exists.
- Frontend smoke E2E passes.
- `git diff --name-only -- server` returns empty output.
- Result document is written before commit.
- Milestone is committed and pushed to `dev`.

## Risks

- Local bootstrap data may not include a skill with labels. If so, live contract comparison can
  verify empty `data` and route ownership, but a richer DB fixture is needed before migrating larger
  skill read APIs.
- Python currently has no auth/session bridge. Owner preview, namespace-only access, private access,
  hidden preview, and SUPER_ADMIN behavior remain Java-owned/deferred.
- Vite regex proxy behavior must be verified with a config test because prefix proxying
  `/api/v1/skills` would be too broad and could accidentally take ownership of un-migrated skill
  APIs.
