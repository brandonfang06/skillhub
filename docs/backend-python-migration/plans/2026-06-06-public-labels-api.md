# Public Labels API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the public labels read API from Java to FastAPI while Java and Python continue to
coexist.

**Architecture:** Python will own the public, read-only labels API group and read directly from the
existing SkillHub PostgreSQL schema. Java remains the source of truth for all mutating/admin label
APIs. Vite dev proxy will route only the public label GET aliases to Python; all other `/api` and
`/oauth2` traffic remains Java-owned.

**Tech Stack:** FastAPI, Python 3.12, `uv + .venv`, SQLAlchemy Core async engine, asyncpg,
pytest, FastAPI TestClient, Vite proxy tests.

---

## Decision

The next backend migration target is the **Public Labels read API**:

| Method | Path | Current Owner | Target Owner | Notes |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/labels` | java | python | Public visible label filters. |
| GET | `/api/web/labels` | java | python | Frontend alias used by the current React app. |

This is a good first real business API because:

- It is public and read-only.
- It does not require session, OAuth, CSRF, API token, RBAC, idempotency, or mutation handling.
- It exercises PostgreSQL read access, which later Python API migrations will also need.
- It is visible in the frontend search workflow, so local E2E can verify Java/Python/Vite
  coexistence.

Rejected next candidates:

- `/.well-known/clawhub.json`: lower risk, but too trivial and does not exercise database access.
- Auth/session APIs: too early because the Python security bridge is not designed yet.
- Skill search/detail/download APIs: higher blast radius and should wait until the Python DB pattern
  is validated on a smaller read model.

## Hard Boundaries

- Do not modify any file under `server/`.
- Do not modify Java migrations, entities, controllers, services, tests, or configuration.
- Do not manually edit generated frontend OpenAPI files.
- Do not migrate `/api/v1/admin/labels` or any label mutation endpoints in this milestone.
- Do not change production routing; only Vite local dev proxy changes are allowed.

Allowed implementation files:

- `server-python/pyproject.toml`
- `server-python/uv.lock`
- `server-python/app/api/labels.py`
- `server-python/app/core/config.py`
- `server-python/app/core/database.py`
- `server-python/app/core/response.py` if a shared envelope helper must be extended
- `server-python/app/main.py`
- `server-python/tests/test_labels.py`
- `server-python/tests/test_label_repository.py`
- `server-python/tests/test_hybrid_makefile.py` only if workflow assertions need a new route
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/results/2026-06-06-public-labels-api.md`
- `web/vite.config.ts`
- `web/vite.config.test.ts`

## Java Contract Reference

Read-only reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/LabelController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/PublicLabelAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLabelDto.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelDefinition.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelTranslation.java`

Existing Java behavior to match:

- `GET /api/v1/labels`
- `GET /api/web/labels`
- Response envelope uses:

```json
{
  "code": 0,
  "msg": "response.success.read",
  "data": [
    {
      "slug": "official",
      "type": "RECOMMENDED",
      "displayName": "Official"
    }
  ],
  "timestamp": "2026-06-06T00:00:00Z",
  "requestId": "..."
}
```

Data rules:

- Read rows from `label_definition`.
- Include only `visible_in_filter = true`.
- Sort by `sort_order ASC, id ASC`, matching Java `findByVisibleInFilterTrueOrderBySortOrderAscIdAsc()`.
- Join translations from `label_translation` by `label_id`.
- `slug` maps from `label_definition.slug`.
- `type` maps from `label_definition.type`.
- `displayName` must use the same fallback rule as Java:
  - Normalize locale by trimming, replacing `_` with `-`, and lowercasing.
  - Prefer active request locale language tag, for example `zh-cn`.
  - Fall back to active request language, for example `zh`.
  - Fall back to `en`.
  - Fall back to the label slug.

## Route Split

During implementation, update route ownership in `docs/backend-python-migration/route-registry.md`:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/labels` | python | Public labels read API. |
| GET | `/api/web/labels` | python | Frontend alias for public labels read API. |
| * | `/api/**` | java | Default owner for everything else. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |

Vite proxy order must be specific before broad:

```ts
proxy: {
  '/api/v1/health': {
    target: 'http://localhost:8081',
    changeOrigin: true,
  },
  '/api/v1/labels': {
    target: 'http://localhost:8081',
    changeOrigin: true,
  },
  '/api/web/labels': {
    target: 'http://localhost:8081',
    changeOrigin: true,
  },
  '/api': {
    target: 'http://localhost:8080',
    changeOrigin: true,
  },
  '/oauth2': {
    target: 'http://localhost:8080',
    changeOrigin: true,
  },
}
```

## File Structure

Create or modify these Python modules:

- `server-python/app/core/config.py`
  - Owns environment parsing for Python backend settings.
  - Provides `DATABASE_URL`.
  - Does not read Java YAML.
- `server-python/app/core/database.py`
  - Owns SQLAlchemy async engine/session lifecycle.
  - Provides dependency functions for app code.
- `server-python/app/api/labels.py`
  - Owns public label route handlers and SQL read model query.
  - Returns existing SkillHub envelope with `response.success.read`.
- `server-python/tests/test_label_repository.py`
  - Tests mapping and locale fallback without needing real PostgreSQL.
- `server-python/tests/test_labels.py`
  - Tests FastAPI routes, envelope, request id, and both path aliases.

## Environment Contract

Python must not depend on Java's `application-local.yml`.

Use one Python-owned environment variable:

```bash
SKILLHUB_DATABASE_URL=postgresql+asyncpg://skillhub:skillhub@localhost:5432/skillhub
```

Windows PowerShell equivalent:

```powershell
$env:SKILLHUB_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub@localhost:5432/skillhub'
```

Default local value may point to the Docker Compose development database, but Ubuntu developers can
override it to the organization PostgreSQL endpoint. Redis and MinIO are not needed for this API.

## Implementation Tasks

### Task 1: Add Failing Public Labels Route Tests

**Files:**

- Create: `server-python/tests/test_labels.py`

- [ ] **Step 1: Write tests for both route aliases and response envelope**

Use dependency override or app state injection so the route test does not require PostgreSQL.

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_public_labels_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.label_reader = lambda locale: [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "Official"}
    ]

    client = TestClient(app)
    response = client.get("/api/v1/labels", headers={"X-Request-Id": "labels-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "labels-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "response.success.read"
    assert response.json()["requestId"] == "labels-test"
    assert response.json()["data"] == [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "Official"}
    ]


def test_public_labels_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.label_reader = lambda locale: [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]

    client = TestClient(app)
    response = client.get("/api/web/labels")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_labels.py -v
```

Expected failure:

- `404 Not Found` for `/api/v1/labels`
- `404 Not Found` for `/api/web/labels`

### Task 2: Add Label Mapping and Locale Fallback Tests

**Files:**

- Create: `server-python/tests/test_label_repository.py`
- Create or modify: `server-python/app/api/labels.py`

- [ ] **Step 1: Write tests for sorting and display name fallback**

```python
from app.api.labels import build_label_response


def test_build_label_response_sorts_visible_labels_and_uses_requested_locale() -> None:
    labels = [
        {"id": 2, "slug": "beta", "type": "RECOMMENDED", "sort_order": 20, "visible_in_filter": True},
        {"id": 1, "slug": "official", "type": "RECOMMENDED", "sort_order": 10, "visible_in_filter": True},
        {"id": 3, "slug": "hidden", "type": "PRIVILEGED", "sort_order": 5, "visible_in_filter": False},
    ]
    translations = [
        {"label_id": 1, "locale": "en", "display_name": "Official"},
        {"label_id": 1, "locale": "zh_CN", "display_name": "官方"},
        {"label_id": 2, "locale": "en", "display_name": "Beta"},
    ]

    assert build_label_response(labels, translations, "zh-CN") == [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "官方"},
        {"slug": "beta", "type": "RECOMMENDED", "displayName": "Beta"},
    ]


def test_build_label_response_falls_back_to_slug_without_translations() -> None:
    labels = [
        {"id": 4, "slug": "internal", "type": "PRIVILEGED", "sort_order": 1, "visible_in_filter": True}
    ]

    assert build_label_response(labels, [], "en") == [
        {"slug": "internal", "type": "PRIVILEGED", "displayName": "internal"}
    ]


def test_build_label_response_falls_back_to_language_then_english_then_slug() -> None:
    labels = [
        {"id": 5, "slug": "localized", "type": "RECOMMENDED", "sort_order": 1, "visible_in_filter": True},
        {"id": 6, "slug": "english-only", "type": "RECOMMENDED", "sort_order": 2, "visible_in_filter": True},
        {"id": 7, "slug": "slug-only", "type": "RECOMMENDED", "sort_order": 3, "visible_in_filter": True},
    ]
    translations = [
        {"label_id": 5, "locale": "zh", "display_name": "中文"},
        {"label_id": 6, "locale": "en", "display_name": "English"},
        {"label_id": 6, "locale": "fr", "display_name": "Francais"},
    ]

    assert build_label_response(labels, translations, "zh-TW") == [
        {"slug": "localized", "type": "RECOMMENDED", "displayName": "中文"},
        {"slug": "english-only", "type": "RECOMMENDED", "displayName": "English"},
        {"slug": "slug-only", "type": "RECOMMENDED", "displayName": "slug-only"},
    ]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_label_repository.py -v
```

Expected failure:

- Import error for `build_label_response` or assertion failure until implementation exists.

### Task 3: Add Python DB Dependencies

**Files:**

- Modify: `server-python/pyproject.toml`
- Modify: `server-python/uv.lock`

- [ ] **Step 1: Add runtime dependencies**

Run:

```bash
cd server-python
uv add "sqlalchemy[asyncio]>=2.0.0" "asyncpg>=0.30.0"
```

Expected:

- `pyproject.toml` contains SQLAlchemy and asyncpg.
- `uv.lock` is updated.

- [ ] **Step 2: Run existing tests**

Run:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest
```

Expected:

- Existing tests still pass except the intentionally failing labels tests until code is implemented.

### Task 4: Implement Configuration and Database Lifecycle

**Files:**

- Create: `server-python/app/core/config.py`
- Create: `server-python/app/core/database.py`
- Modify: `server-python/app/main.py`

- [ ] **Step 1: Add config module**

```python
from dataclasses import dataclass
import os


DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub@localhost:5432/skillhub"


@dataclass(frozen=True)
class Settings:
    database_url: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("SKILLHUB_DATABASE_URL", DEFAULT_DATABASE_URL),
    )
```

- [ ] **Step 2: Add database module**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


async def dispose_database_engine(engine: AsyncEngine) -> None:
    await engine.dispose()


async def iter_engine(app_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    yield app_engine
```

- [ ] **Step 3: Register settings and DB engine in app lifespan**

Use FastAPI lifespan so tests can override `app.state.label_reader` without opening PostgreSQL.

Expected shape in `create_app()`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.db_engine = create_database_engine(settings)
    try:
        yield
    finally:
        await dispose_database_engine(app.state.db_engine)
```

- [ ] **Step 4: Run health tests**

Run:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_health.py -v
```

Expected:

- Health tests pass and do not require a live database connection.

### Task 5: Implement Public Labels API

**Files:**

- Create or modify: `server-python/app/api/labels.py`
- Modify: `server-python/app/main.py`

- [ ] **Step 1: Add label response builder**

```python
from collections import defaultdict
from typing import Any


LabelRow = dict[str, Any]
TranslationRow = dict[str, Any]


def build_label_response(
    labels: list[LabelRow],
    translations: list[TranslationRow],
    locale: str | None,
) -> list[dict[str, str]]:
    translations_by_label: dict[int, list[TranslationRow]] = defaultdict(list)
    for translation in translations:
        translations_by_label[int(translation["label_id"])].append(translation)

    visible_labels = [label for label in labels if bool(label["visible_in_filter"])]
    visible_labels.sort(key=lambda label: (int(label["sort_order"]), int(label["id"])))

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
        for label in visible_labels
    ]
```

- [ ] **Step 2: Add display name resolver**

```python
def normalize_locale(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().replace("_", "-").lower()


def locale_language(value: str | None) -> str:
    normalized = normalize_locale(value)
    return normalized.split("-", 1)[0] if normalized else ""


def resolve_display_name(
    slug: str,
    translations: list[TranslationRow],
    locale: str | None,
) -> str:
    values: dict[str, str] = {}
    for translation in translations:
        normalized = normalize_locale(str(translation["locale"]))
        display_name = str(translation["display_name"])
        if normalized not in values:
            values[normalized] = display_name

    candidates = [normalize_locale(locale), locale_language(locale), "en"]
    for candidate in candidates:
        value = values.get(candidate)
        if value and value.strip():
            return value

    return slug
```

- [ ] **Step 3: Add async database reader**

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def read_visible_labels(engine: AsyncEngine, locale: str | None) -> list[dict[str, str]]:
    async with engine.connect() as connection:
        label_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, slug, type, visible_in_filter, sort_order
                    FROM label_definition
                    WHERE visible_in_filter = true
                    ORDER BY sort_order ASC, id ASC
                    """
                )
            )
        ).mappings().all()

        label_ids = [row["id"] for row in label_rows]
        if not label_ids:
            return []

        translation_rows = (
            await connection.execute(
                text(
                    """
                    SELECT label_id, locale, display_name
                    FROM label_translation
                    WHERE label_id = ANY(:label_ids)
                    ORDER BY label_id ASC, locale ASC
                    """
                ),
                {"label_ids": label_ids},
            )
        ).mappings().all()

    return build_label_response([dict(row) for row in label_rows], [dict(row) for row in translation_rows], locale)
```

- [ ] **Step 4: Add route handler for both aliases**

```python
from fastapi import APIRouter, Request

from app.core.response import ok

router = APIRouter()


def requested_locale(request: Request) -> str | None:
    accept_language = request.headers.get("Accept-Language")
    if not accept_language:
        return None
    return accept_language.split(",", 1)[0].strip() or None


@router.get("/api/v1/labels")
@router.get("/api/web/labels")
async def list_visible_labels(request: Request) -> dict[str, object]:
    locale = requested_locale(request)
    reader = getattr(request.app.state, "label_reader", None)
    if reader is not None:
        data = reader(locale)
    else:
        data = await read_visible_labels(request.app.state.db_engine, locale)
    return ok("response.success.read", data, request)
```

- [ ] **Step 5: Include router in app**

```python
from app.api.labels import router as labels_router

app.include_router(labels_router)
```

- [ ] **Step 6: Run labels tests**

Run:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_labels.py tests/test_label_repository.py -v
```

Expected:

- Labels route and mapping tests pass.

### Task 6: Update Route Registry and Vite Proxy

**Files:**

- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`

- [ ] **Step 1: Add route ownership rows**

Add these rows above the fallback `/api/**` row:

```markdown
| GET | `/api/v1/labels` | python | Public visible label filters. |
| GET | `/api/web/labels` | python | Frontend alias for public visible label filters. |
```

- [ ] **Step 2: Update Vite proxy**

Add `/api/v1/labels` and `/api/web/labels` before `/api`.

- [ ] **Step 3: Update Vite proxy tests**

Assert both routes target `http://localhost:8081` and `/api` fallback remains
`http://localhost:8080`.

- [ ] **Step 4: Run proxy tests**

Run:

```bash
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected:

- Vite proxy tests pass.

### Task 7: Contract Comparison Against Java

**Files:**

- No committed server files.
- Temporary curl output may be inspected but must not be committed.

- [ ] **Step 1: Start Java, Python, and Vite**

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

macOS:

```bash
make dev-all-hybrid
```

Ubuntu:

Use organization PostgreSQL/Redis/MinIO, then start Java, Python, and Vite separately as documented
in `SDLC-README.md`.

- [ ] **Step 2: Compare Java and Python direct responses**

Before Vite proxy is switched, or by temporarily calling Java directly:

```bash
curl -s http://localhost:8080/api/v1/labels
curl -s http://localhost:8081/api/v1/labels
```

Expected:

- Both return `code = 0`.
- Both return `msg = response.success.read`.
- `data` items have the same `slug`, `type`, and `displayName` values.
- `timestamp` and `requestId` may differ.

- [ ] **Step 3: Verify Vite proxy ownership**

```bash
curl -i http://localhost:3000/api/v1/labels
curl -i http://localhost:3000/api/web/labels
curl -i http://localhost:3000/api/v1/health
```

Expected:

- All three routes return from Python on port `8081`.
- Other `/api` routes still proxy to Java on port `8080`.

### Task 8: Frontend Smoke E2E

**Files:**

- Modify frontend E2E only if an existing smoke test needs a route assertion.

- [ ] **Step 1: Run smoke E2E through Vite**

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

macOS:

```bash
make test-e2e-smoke-hybrid
```

Ubuntu:

```bash
cd web
corepack pnpm run test:e2e:smoke
```

Expected:

- Smoke E2E passes.
- Search page label filters do not regress.

### Task 9: Record Result, Boundary Check, Commit, Push

**Files:**

- Create: `docs/backend-python-migration/results/2026-06-06-public-labels-api.md`

- [ ] **Step 1: Run final Python tests**

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest
```

Expected:

- All Python tests pass.

- [ ] **Step 2: Run final Vite proxy test**

```bash
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected:

- Vite proxy tests pass.

- [ ] **Step 3: Confirm Java boundary**

```bash
git diff --name-only -- server
```

Expected:

- No output.

- [ ] **Step 4: Write result document**

Include:

- Routes changed
- Owner before/after
- Tests run
- Java/Python contract comparison result
- E2E result
- Risks
- Follow-up

- [ ] **Step 5: Commit and push**

```bash
git add server-python docs/backend-python-migration web/vite.config.ts web/vite.config.test.ts
git commit -m "Migrate public labels API to Python"
git push origin dev
```

## Risks and Mitigations

- **Locale parity risk:** Python must match Java's normalized locale fallback exactly. Mitigation:
  keep the explicit language-tag, language, `en`, slug fallback tests before implementation.
- **Database URL drift:** Python uses `SKILLHUB_DATABASE_URL`, not Java YAML. Mitigation: document
  the env var in result docs and SDLC docs if needed.
- **Route alias risk:** Frontend uses `/api/web/labels`; migrating only `/api/v1/labels` would not
  validate the UI path. Mitigation: migrate both aliases together.
- **SQL dialect risk:** `ANY(:label_ids)` is PostgreSQL-specific. This is acceptable because
  SkillHub uses PostgreSQL 16, but tests should keep mapping logic independent of a live DB.

## Plan Self-Review

- The plan covers API contract, DB read model, Vite proxy ownership, route registry, tests, E2E,
  result docs, commit, and push.
- No Java file is modified by the plan.
- No protected/mutating/auth endpoint is included.
- Java locale fallback was checked against `LabelLocalizationService`; the plan now encodes the
  exact normalized language-tag, language, `en`, slug order.
