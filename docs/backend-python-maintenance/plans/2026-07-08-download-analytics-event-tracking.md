# Download Analytics Event Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record each successful published skill download in a dedicated table and expose operator-readable download history without changing the existing upstream-compatible download counter behavior.

**Architecture:** Keep the existing `skill.download_count` and `skill_version_stats.download_count` counters as the source for public counts. Add a separate `local_skill_download_event` write path and query API so the organization-specific analytics feature stays isolated from upstream parity code. The first milestone is backend/API only; frontend reporting UI can be added after the API contract is proven.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, PostgreSQL, bundled upstream Flyway SQL baseline plus local Python-owned SQL migrations through `server-python/app/migrations.py`, pytest, generated OpenAPI TypeScript types.

---

## Milestone Boundary

This milestone answers:

- Which skill/version was downloaded.
- Which authenticated user downloaded it, when the request has a user principal.
- Whether the download came from `web`, `api`, or `cli`.
- How operators can filter download events by skill, version, user, source, and time.

This milestone intentionally does not:

- Force authentication for currently anonymous public downloads.
- Change existing download counter semantics.
- Add a frontend analytics page.
- Store failed download attempts.
- Use `audit_log` as the analytics table.

Anonymous downloads are recorded with `user_id = NULL`. If the deployment requires every download to be attributable to a user, that should be a separate policy milestone that changes download authorization rules.

## Upstream Maintenance Strategy

This is an organization extension, not an upstream parity patch. Keep it isolated so future upstream release follow-up can compare:

- upstream download route behavior,
- existing counter updates,
- local `record_skill_download_event` hook.

When following upstream, the only recurring check should be whether published download success still passes through the same counter/update boundary. If upstream changes the download route, reattach the event hook after successful published downloads and keep the event schema/query API unchanged unless a product requirement changes.

Do not add this organization extension as `server-python/app/db/migration/V44__...`. The `V*__*.sql` namespace mirrors upstream Flyway numbering, so a local V44 would collide with a future upstream V44. Use `server-python/app/db/local_migration/` and a local tracking table instead. The upstream-covered baseline remains at the latest followed upstream Flyway version until an upstream release changes it.

## Local Migration Tracking Contract

This milestone introduces a Python-owned local migration layer for organization-specific schema that is not part of upstream SkillHub:

- Local migration files live under `server-python/app/db/local_migration/`.
- Applied local migrations are recorded in `local_schema_migration`.
- `local_schema_migration` is a local extension tracking table; do not map it to an upstream Flyway version.
- `server-python/app/db/migration/V*__*.sql` remains reserved for the upstream-followed Flyway schema baseline.
- When following upstream schema changes, update the upstream baseline separately and keep the local migration chain intact.
- Before accepting an upstream database migration, check whether upstream added an equivalent download analytics feature. If it did, write an explicit migration/retirement plan for `local_skill_download_event` instead of silently dropping or renaming it.

## Files

- Create: `server-python/app/db/local_migration/20260708_01__local_skill_download_event.sql`
- Modify: `server-python/app/migrations.py`
- Modify: `server-python/tests/test_schema_migration_baseline.py`
- Create: `server-python/app/download_analytics/__init__.py`
- Create: `server-python/app/download_analytics/repository.py`
- Create: `server-python/app/api/download_analytics.py`
- Modify: `server-python/app/main.py`
- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/tests/test_skill_download.py`
- Create: `server-python/tests/test_download_analytics.py`
- Modify: `web/src/api/generated/schema.d.ts`
- Create: `docs/backend-python-maintenance/results/2026-07-08-download-analytics-event-tracking.md`

## API Contract

Add two read endpoints:

- `GET /api/v1/admin/download-events`
  - For platform operators.
  - Requires one of `SUPER_ADMIN`, `SKILL_ADMIN`, or `AUDITOR`.
  - Supports filters: `namespace`, `slug`, `version`, `userId`, `source`, `startTime`, `endTime`, `page`, `size`.

- `GET /api/web/skills/{namespace}/{slug}/download-events`
  - For skill-scoped analytics.
  - Allows `SUPER_ADMIN`, `SKILL_ADMIN`, `AUDITOR`, skill owner, or namespace `OWNER`/`ADMIN`.
  - Supports filters: `version`, `userId`, `source`, `startTime`, `endTime`, `page`, `size`.

Response shape:

```json
{
  "items": [
    {
      "id": 1,
      "skillId": 100,
      "skillVersionId": 200,
      "namespace": "team-a",
      "slug": "demo-skill",
      "version": "1.0.0",
      "source": "web",
      "userId": "user-a",
      "username": "User A",
      "requestId": "request-1",
      "ipAddress": "127.0.0.1",
      "userAgent": "Mozilla/5.0",
      "createdAt": "2026-07-08T10:30:00Z"
    }
  ],
  "total": 1,
  "page": 0,
  "size": 20
}
```

## Task 1: Local Schema Extension Migration

**Files:**
- Create: `server-python/app/db/local_migration/20260708_01__local_skill_download_event.sql`
- Modify: `server-python/app/migrations.py`
- Modify: `server-python/tests/test_schema_migration_baseline.py`

- [ ] **Step 1: Write the migration test first**

Add assertions that the upstream Flyway baseline remains at the currently followed upstream version, local migration discovery finds the download event extension, and existing databases without `local_skill_download_event` apply the local migration after the upstream baseline path.

Target test names:

```python
def test_baseline_revision_tracks_bundled_python_migration_snapshot() -> None:
    latest_flyway = max(migrations.flyway_migration_files(FLYWAY_DIR), key=lambda item: item.version)

    assert migrations.BASELINE_FLYWAY_VERSION == latest_flyway.version
    assert migrations.BASELINE_REVISION == "skillhub_flyway_v43_baseline"
    assert latest_flyway.path.name == "V43__user_account_system_account.sql"


def test_local_migration_files_include_download_event_extension() -> None:
    local_migrations = migrations.local_migration_files(ROOT / "server-python" / "app" / "db" / "local_migration")

    assert [item.identifier for item in local_migrations] == ["20260708_01"]
    assert local_migrations[0].path.name == "20260708_01__local_skill_download_event.sql"


def test_existing_v43_python_database_applies_local_migrations_after_baseline() -> None:
    connection = FakeConnection(
        existing_tables={"user_account"},
        existing_columns={("user_account", "system_account")},
    )

    asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

    assert any("CREATE TABLE IF NOT EXISTS local_schema_migration" in statement for statement in connection.executed)
    assert any("CREATE TABLE local_skill_download_event" in statement for statement in connection.executed)
    assert any("INSERT INTO local_schema_migration" in statement for statement in connection.executed)
    assert any(migrations.BASELINE_REVISION in statement for statement in connection.executed)
```

- [ ] **Step 2: Run the migration test and verify it fails**

Run:

```powershell
cd server-python
uv run pytest tests/test_schema_migration_baseline.py -q
```

Expected: failure showing `local_migration_files`, the local migration SQL, or the local migration tracking table does not exist yet.

- [ ] **Step 3: Add local migration SQL**

Create `server-python/app/db/local_migration/20260708_01__local_skill_download_event.sql`:

```sql
CREATE TABLE local_skill_download_event (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
    skill_version_id BIGINT NOT NULL REFERENCES skill_version(id) ON DELETE CASCADE,
    user_id VARCHAR(128) REFERENCES user_account(id),
    namespace_slug VARCHAR(64) NOT NULL,
    skill_slug VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL CHECK (source IN ('api', 'web', 'cli')),
    request_id VARCHAR(64),
    client_ip VARCHAR(64),
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_local_skill_download_event_skill_created_at
    ON local_skill_download_event(skill_id, created_at DESC);

CREATE INDEX idx_local_skill_download_event_version_created_at
    ON local_skill_download_event(skill_version_id, created_at DESC);

CREATE INDEX idx_local_skill_download_event_user_created_at
    ON local_skill_download_event(user_id, created_at DESC);

CREATE INDEX idx_local_skill_download_event_namespace_slug_created_at
    ON local_skill_download_event(namespace_slug, skill_slug, created_at DESC);
```

- [ ] **Step 4: Add Python-owned local migration handling**

Keep the upstream baseline constants unchanged:

```python
BASELINE_FLYWAY_VERSION = 43
BASELINE_REVISION = "skillhub_flyway_v43_baseline"
```

Add local migration discovery and application helpers:

```python
LOCAL_MIGRATION_DIR = ROOT / "server-python" / "app" / "db" / "local_migration"


@dataclass(frozen=True)
class LocalMigration:
    identifier: str
    description: str
    path: Path


def local_migration_files(local_dir: Path = LOCAL_MIGRATION_DIR) -> list[LocalMigration]:
    migrations: list[LocalMigration] = []
    for path in local_dir.glob("*__*.sql"):
        identifier, description = path.name.split("__", 1)
        migrations.append(
            LocalMigration(
                identifier=identifier,
                description=description.removesuffix(".sql"),
                path=path,
            )
        )
    return sorted(migrations, key=lambda item: item.identifier)
```

Apply local migrations after baseline handling:

```python
async def apply_local_schema_migrations(
    connection: DatabaseConnection,
    local_dir: Path = LOCAL_MIGRATION_DIR,
) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS local_schema_migration (
            identifier VARCHAR(64) PRIMARY KEY,
            description VARCHAR(256) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for migration in local_migration_files(local_dir):
        already_applied = await connection.fetchval(
            "SELECT 1 FROM local_schema_migration WHERE identifier = $1",
            migration.identifier,
        )
        if already_applied is not None:
            continue
        await connection.execute(migration.path.read_text(encoding="utf-8"))
        await connection.execute(
            "INSERT INTO local_schema_migration (identifier, description) VALUES ($1, $2)",
            migration.identifier,
            migration.description,
        )
```

Call `await apply_local_schema_migrations(connection)` at the end of `upgrade_database` for both fresh and existing databases. Do not call it from `stamp_existing_database`; `stamp` remains a baseline-stamp operation, while `upgrade` applies local extension schema.

- [ ] **Step 5: Run migration tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_schema_migration_baseline.py -q
```

Expected: all tests pass.

## Task 2: Download Event Writer

**Files:**
- Create: `server-python/app/download_analytics/__init__.py`
- Create: `server-python/app/download_analytics/repository.py`
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/tests/test_skill_download.py`

- [ ] **Step 1: Write failing tests for event recording**

Add tests that verify:

- published downloads still increment `skill.download_count`;
- published downloads insert one `local_skill_download_event`;
- `UPLOADED` and `PENDING_REVIEW` preview downloads do not insert events;
- route handlers pass `web`, `api`, and `cli` source metadata correctly.

Example repository assertion:

```python
assert any("INSERT INTO local_skill_download_event" in statement for statement in connection.statements)
assert connection.params[-1]["user_id"] == "local-user"
assert connection.params[-1]["source"] == "web"
```

- [ ] **Step 2: Run the targeted download tests and verify they fail**

Run:

```powershell
cd server-python
uv run pytest tests/test_skill_download.py -q
```

Expected: failure because the event writer and route metadata do not exist yet.

- [ ] **Step 3: Add the event context and writer**

Create `server-python/app/download_analytics/repository.py` with a small write helper:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text


DownloadSource = Literal["api", "web", "cli"]


@dataclass(frozen=True)
class DownloadEventContext:
    user_id: str | None
    source: DownloadSource
    request_id: str | None
    client_ip: str | None
    user_agent: str | None


async def record_skill_download_event(
    connection: Any,
    *,
    skill_id: int,
    skill_version_id: int,
    namespace: str,
    slug: str,
    version: str,
    context: DownloadEventContext,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO local_skill_download_event (
                skill_id, skill_version_id, user_id, namespace_slug, skill_slug,
                version, source, request_id, client_ip, user_agent, created_at
            )
            VALUES (
                :skill_id, :skill_version_id, :user_id, :namespace, :slug,
                :version, :source, :request_id, :client_ip, :user_agent, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "skill_id": skill_id,
            "skill_version_id": skill_version_id,
            "user_id": context.user_id,
            "namespace": namespace,
            "slug": slug,
            "version": version,
            "source": context.source,
            "request_id": context.request_id,
            "client_ip": context.client_ip,
            "user_agent": context.user_agent,
        },
    )
```

- [ ] **Step 4: Hook the writer after successful published downloads**

Change `read_skill_download_version` to accept optional `download_event_context: DownloadEventContext | None = None`.

After the existing counter update call, add:

```python
if download_event_context is not None:
    await record_skill_download_event(
        connection,
        skill_id=int(skill_row["id"]),
        skill_version_id=int(version_row["id"]),
        namespace=namespace,
        slug=str(skill_row["slug"]),
        version=str(version_row["version"]),
        context=download_event_context,
    )
```

Pass the context through `read_skill_download_latest` and `read_skill_download_tag` to the final version download helper.

- [ ] **Step 5: Build route metadata without changing auth behavior**

In `server-python/app/api/skills.py`, add a helper:

```python
def _download_source(request: Request) -> str:
    path = request.url.path
    if path.startswith("/api/cli/"):
        return "cli"
    if path.startswith("/api/web/"):
        return "web"
    return "api"


def _download_event_context(request: Request, user_id: str | None) -> DownloadEventContext:
    return DownloadEventContext(
        user_id=user_id,
        source=_download_source(request),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
```

Pass `_download_event_context(request, current_user_id)` into each real download reader call. Keep test override readers compatible by leaving custom reader calls with the existing argument shape.

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_skill_download.py tests/test_publish_review_download_session_flow.py -q
```

Expected: all tests pass.

## Task 3: Download Analytics Query API

**Files:**
- Modify: `server-python/app/download_analytics/repository.py`
- Create: `server-python/app/api/download_analytics.py`
- Modify: `server-python/app/main.py`
- Create: `server-python/tests/test_download_analytics.py`

- [ ] **Step 1: Write API and repository tests first**

Test cases:

- `SUPER_ADMIN`, `SKILL_ADMIN`, and `AUDITOR` can query `/api/v1/admin/download-events`.
- normal users cannot query the admin endpoint.
- skill owner can query `/api/web/skills/{namespace}/{slug}/download-events` for their skill.
- namespace `OWNER` and `ADMIN` can query skill-scoped events.
- unrelated namespace member cannot see another skill's download events.
- filters bind exact SQL parameters for user, version, source, and time range.
- response uses camelCase fields matching the API contract above.

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
cd server-python
uv run pytest tests/test_download_analytics.py -q
```

Expected: failure because repository and routes do not exist.

- [ ] **Step 3: Add repository read helpers**

Extend `repository.py` with:

```python
class DownloadAnalyticsError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_platform_download_event_reader(platform_roles: list[str]) -> None:
    if set(platform_roles).isdisjoint({"SUPER_ADMIN", "SKILL_ADMIN", "AUDITOR"}):
        raise DownloadAnalyticsError("error.downloadAnalytics.readDenied", status_code=403)
```

Implement `list_admin_download_events` and `list_skill_download_events` using SQL text queries against `local_skill_download_event`, joining `user_account` for `username`.

- [ ] **Step 4: Add FastAPI routes**

Create `server-python/app/api/download_analytics.py` with:

```python
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request

router = APIRouter(tags=["Download Analytics"])
```

Add route handlers for:

```python
@router.get("/api/v1/admin/download-events")
async def list_admin_download_events_route(
    request: Request,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    namespace: str | None = None,
    slug: str | None = None,
    version: str | None = None,
    userId: str | None = None,
    source: str | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    try:
        return await list_admin_download_events(
            request.app.state.db_engine,
            page=page,
            size=size,
            namespace=namespace,
            slug=slug,
            version=version,
            user_id=userId,
            source=source,
            start_time=startTime,
            end_time=endTime,
            platform_roles=platform_roles(user),
        )
    except DownloadAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/api/web/skills/{namespace}/{slug}/download-events")
async def list_skill_download_events_route(
    namespace: str,
    slug: str,
    request: Request,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    version: str | None = None,
    userId: str | None = None,
    source: str | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    user = dict(await resolve_current_user_or_401(request, mock_user_id, None))
    try:
        return await list_skill_download_events(
            request.app.state.db_engine,
            namespace=namespace,
            slug=slug,
            page=page,
            size=size,
            version=version,
            user_id=userId,
            source=source,
            start_time=startTime,
            end_time=endTime,
            actor_user_id=str(user["userId"]),
            platform_roles=platform_roles(user),
        )
    except DownloadAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
```

Use `resolve_current_user_or_401`, `platform_roles(user)`, and namespace-role checks in the repository. Reject bearer API-token principals for admin route using the existing admin-route pattern if the route accepts `Authorization`.

- [ ] **Step 5: Register the router**

Modify `server-python/app/main.py`:

```python
from app.api.download_analytics import router as download_analytics_router

app.include_router(download_analytics_router)
```

- [ ] **Step 6: Run API tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_download_analytics.py tests/test_route_policy_enforcement.py tests/test_route_registry.py -q
```

Expected: all tests pass. If route registry tests require explicit route ownership documentation, update the relevant route registry fixture in the same task.

## Task 4: OpenAPI And Operator Documentation

**Files:**
- Modify: `web/src/api/generated/schema.d.ts`
- Create: `docs/backend-python-maintenance/results/2026-07-08-download-analytics-event-tracking.md`

- [ ] **Step 1: Generate OpenAPI types**

Start the backend on port 8080 after applying migrations, then run:

```powershell
cd web
pnpm run generate-api
```

Expected: `web/src/api/generated/schema.d.ts` includes the new download analytics endpoints.

- [ ] **Step 2: Add result documentation**

Create `docs/backend-python-maintenance/results/2026-07-08-download-analytics-event-tracking.md` with:

```markdown
# Download Analytics Event Tracking Result

## Scope

- Added `local_skill_download_event` as a dedicated organization analytics table.
- Kept existing public download counters unchanged.
- Added backend query APIs for platform operators and skill-scoped managers.

## Operator Notes

- Authenticated downloads record `user_id`.
- Anonymous public downloads record `user_id = NULL`.
- The feature does not force login for public downloads.
- The event table is separate from `audit_log` to avoid turning audit logs into high-volume analytics.

## Verification

- `uv run pytest tests/test_schema_migration_baseline.py -q`
- `uv run pytest tests/test_skill_download.py tests/test_publish_review_download_session_flow.py -q`
- `uv run pytest tests/test_download_analytics.py tests/test_route_policy_enforcement.py tests/test_route_registry.py -q`
- `pnpm run generate-api`
```

- [ ] **Step 3: Run final backend verification**

Run:

```powershell
cd server-python
uv run pytest tests/test_schema_migration_baseline.py tests/test_skill_download.py tests/test_publish_review_download_session_flow.py tests/test_download_analytics.py tests/test_route_policy_enforcement.py tests/test_route_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run repository checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; changed files match this plan.

## Review Checklist

- The event table is independent from `audit_log`.
- The existing download counter behavior still increments only for `PUBLISHED` downloads.
- Preview/review downloads do not create analytics events.
- CLI downloads are recorded with `source = 'cli'`.
- Anonymous downloads are recorded with `user_id = NULL`.
- Admin-wide reads require platform roles.
- Skill-scoped reads require owner, namespace manager, or platform role.
- Fresh DB and existing V43 DB schema upgrade paths both create `local_skill_download_event`.
- OpenAPI generated types are updated after route changes.

## Commit Plan

Use small commits:

1. `feat(schema): add skill download event migration`
2. `feat(downloads): record skill download events`
3. `feat(admin): expose download analytics API`
4. `docs: record download analytics milestone`
