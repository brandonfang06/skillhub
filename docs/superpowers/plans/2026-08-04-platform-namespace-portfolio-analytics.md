# Platform Namespace Portfolio Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a `SUPER_ADMIN` Namespace Analytics page that summarizes eligible catalog skills, distinct maintainers, lifetime downloads, and selected-period downloads per namespace with reproducible filters and Download Events drill-down.

**Architecture:** Add a read-only FastAPI route backed by a dedicated live-aggregation SQL repository. Expose a focused generated OpenAPI contract, consume it through the existing frontend API/TanStack Query layers, and keep all page state in TanStack Router search parameters. Integrate the canonical subpath baseline before touching its shared router/API runtime files so root and `/skillhub` deployments use one base-path mechanism.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy text queries, PostgreSQL, pytest, React 19, TypeScript, TanStack Router/Query, Tailwind, Vitest, Playwright, `uv`, and pnpm 10.33.0 through Corepack.

---

## File Map

- Create `server-python/app/namespace_analytics/contracts.py`: Pydantic response models for the focused OpenAPI contract.
- Create `server-python/app/namespace_analytics/repository.py`: filter normalization, period resolution, live SQL aggregation, sorting, and row projection.
- Create `server-python/app/namespace_analytics/__init__.py`: stable package exports.
- Create `server-python/app/api/namespace_analytics.py`: transport-only protected GET route.
- Modify `server-python/app/main.py`: register the new router.
- Create `server-python/tests/test_namespace_analytics.py`: repository, route, auth, validation, envelope, and OpenAPI tests.
- Create `server-python/scripts/export_namespace_analytics_openapi.py`: deterministic focused FastAPI OpenAPI exporter.
- Modify `web/package.json`: add the focused generate command.
- Create `web/src/api/generated/namespace-analytics-openapi.json`: generated contract input.
- Create `web/src/api/generated/namespace-analytics-schema.d.ts`: generated TypeScript contract.
- Modify `web/src/api/types.ts`: expose strict frontend aliases based on the generated contract.
- Modify `web/src/api/client.ts` and `web/src/api/client.test.ts`: add URL serialization and typed API method.
- Create `web/src/features/admin/use-namespace-analytics.ts` and its test: TanStack Query boundary.
- Create `web/src/features/admin/namespace-analytics-search.ts` and its test: URL filter parsing, default period resolution, and deterministic navigation state.
- Create `web/src/pages/admin/namespace-analytics.tsx` and its test: approved summary-first UI, filters, sortable table, pagination, states, and drill-down.
- Modify `web/src/pages/admin/download-events.tsx` and its test: initialize filters from incoming router search parameters.
- Modify `web/src/app/router.tsx` and `web/src/app/router.test.ts`: protected logical route plus validated analytics/download search.
- Modify `web/src/shared/components/user-menu.tsx` and its test: `SUPER_ADMIN` menu entry.
- Modify `web/src/i18n/locales/en.json`, `zh.json`, and `zh-TW.json`: page/menu text.
- Modify `web/e2e/subpath-deployment.spec.ts`: production-bundle `/skillhub` route/API/drill-down coverage after the subpath baseline is integrated.
- Modify `docs/backend-python-migration/route-registry.md` and `server-python/tests/test_route_registry.py`: record the Python-owned local admin read route.
- Create `docs/backend-python-maintenance/results/2026-08-04-namespace-analytics.md`: final commands, counts, limitations, and acceptance URL.

## Task 1: Backend Contracts And Period Rules

**Files:**
- Create: `server-python/app/namespace_analytics/contracts.py`
- Create: `server-python/app/namespace_analytics/repository.py`
- Create: `server-python/app/namespace_analytics/__init__.py`
- Test: `server-python/tests/test_namespace_analytics.py`

- [ ] **Step 1: Write failing unit tests for period defaults and validation**

Define tests around this public repository API:

```python
resolved = resolve_period(None, None, now=datetime(2026, 8, 4, tzinfo=UTC))
assert resolved.start_time == datetime(2026, 7, 5, tzinfo=UTC)
assert resolved.end_time == datetime(2026, 8, 4, tzinfo=UTC)

with pytest.raises(NamespaceAnalyticsError, match="error.namespaceAnalytics.invalidTimeRange"):
    resolve_period("2026-08-04T00:00:00Z", "2026-08-03T00:00:00Z")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
cd server-python
uv --no-cache run pytest tests/test_namespace_analytics.py -q
```

Expected: collection or import failure because `app.namespace_analytics` does not exist.

- [ ] **Step 3: Add minimal period and contract types**

Implement immutable `ResolvedPeriod`, `NamespaceAnalyticsError`, and `resolve_period`. Define Pydantic models with the exact API keys:

```python
class NamespaceAnalyticsSummary(BaseModel):
    namespaceCount: int
    maintainerCount: int
    skillCount: int
    lifetimeDownloads: int
    periodDownloads: int

class NamespaceAnalyticsPeriod(BaseModel):
    startTime: datetime
    endTime: datetime
    source: str | None
    retentionMonths: int

class NamespaceAnalyticsItem(BaseModel):
    namespaceId: int
    slug: str
    displayName: str
    type: str
    status: str
    maintainerCount: int
    skillCount: int
    lifetimeDownloads: int
    periodDownloads: int
```

Add the paged data model and the standard `code/msg/data/timestamp/requestId` envelope model.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Task 1 pytest command. Expected: the period tests pass.

- [ ] **Step 5: Commit the period/contract slice**

Commit only the three package files and focused test with subject:

```text
feat(analytics): define namespace analytics contract
```

## Task 2: Live Aggregation Repository

**Files:**
- Modify: `server-python/app/namespace_analytics/repository.py`
- Modify: `server-python/tests/test_namespace_analytics.py`

- [ ] **Step 1: Write failing repository projection and SQL-invariant tests**

Use a fake async engine that returns a summary mapping then row mappings. Assert:

```python
result = await list_namespace_analytics(
    engine,
    query=" platform ",
    namespace_type="ALL",
    namespace_status="ACTIVE",
    start_time="2026-07-05T00:00:00Z",
    end_time="2026-08-04T00:00:00Z",
    source="web",
    sort="periodDownloads",
    direction="desc",
    page=0,
    size=20,
    retention_months=12,
)
assert result["summary"]["maintainerCount"] == 3
assert result["items"][0]["slug"] == "global"
assert result["period"]["source"] == "web"
```

Also inspect the executed SQL and require these semantic guards:

```text
s.status = 'ACTIVE'
s.hidden = FALSE
sv.status = 'PUBLISHED'
COUNT(DISTINCT es.owner_id)
de.skill_id = es.skill_id
de.created_at >= CAST(:start_time AS timestamptz)
de.created_at <= CAST(:end_time AS timestamptz)
LEFT JOIN
```

Add parametrized tests for search/type/status/source, all sort keys, both directions, page-size clamping, zero metrics, and multiple published versions counting one skill.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: failure because `list_namespace_analytics` and the aggregation SQL are absent.

- [ ] **Step 3: Implement the smallest repository query**

Use a shared CTE prefix for both summary and page queries:

```sql
WITH filtered_namespaces AS (...),
eligible_skills AS (
  SELECT s.id AS skill_id, s.namespace_id, s.owner_id, s.download_count
  FROM skill s
  WHERE s.status = 'ACTIVE'
    AND s.hidden = FALSE
    AND EXISTS (
      SELECT 1 FROM skill_version sv
      WHERE sv.skill_id = s.id AND sv.status = 'PUBLISHED'
    )
),
period_by_skill AS (
  SELECT de.skill_id, COUNT(*) AS period_downloads
  FROM local_skill_download_event de
  JOIN eligible_skills es ON es.skill_id = de.skill_id
  WHERE de.created_at >= CAST(:start_time AS timestamptz)
    AND de.created_at <= CAST(:end_time AS timestamptz)
    AND (:source IS NULL OR de.source = :source)
  GROUP BY de.skill_id
),
namespace_metrics AS (... LEFT JOIN eligible_skills ... LEFT JOIN period_by_skill ...)
```

Use a fixed Python mapping from API sort keys to SQL identifiers. Never interpolate user input directly. Compute the summary without pagination and de-duplicate `owner_id` across all filtered namespaces.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: all repository tests pass and executed parameters contain normalized enum/date/page values.

- [ ] **Step 5: Commit the repository slice**

```text
feat(analytics): aggregate namespace portfolio metrics
```

## Task 3: Protected FastAPI Route And Focused OpenAPI

**Files:**
- Create: `server-python/app/api/namespace_analytics.py`
- Modify: `server-python/app/main.py`
- Modify: `server-python/tests/test_namespace_analytics.py`
- Create: `server-python/scripts/export_namespace_analytics_openapi.py`
- Modify: `web/package.json`
- Create: `web/src/api/generated/namespace-analytics-openapi.json`
- Create: `web/src/api/generated/namespace-analytics-schema.d.ts`

- [ ] **Step 1: Write failing route tests**

Cover session/mock `SUPER_ADMIN` success, no session `401`, normal user `403`, `SKILL_ADMIN` `403`, bearer API token rejection, invalid enums, reversed dates, bounds, envelope, request ID, and OpenAPI schema presence.

```python
response = client.get(
    "/api/v1/admin/namespace-analytics",
    headers={"X-Mock-User-Id": "platform-admin", "X-Request-Id": "analytics-test"},
)
assert response.status_code == 200
assert response.json()["requestId"] == "analytics-test"
assert response.json()["data"]["period"]["retentionMonths"] == 12
```

- [ ] **Step 2: Run route tests and verify RED**

Expected: `404` for the new path.

- [ ] **Step 3: Implement the transport-only route**

The route must call, in order:

```python
await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
data = await list_namespace_analytics(...)
return ok("response.success.read", data, request)
```

Use FastAPI `Literal` query types for enum-like fields, `page ge=0`, `size ge=1 le=100`, and the Pydantic envelope as `response_model`.

- [ ] **Step 4: Verify route GREEN**

Run the complete `test_namespace_analytics.py`. Expected: all pass.

- [ ] **Step 5: Add and run focused OpenAPI generation**

Mirror the review exporter: create a minimal FastAPI app, include only the namespace analytics router, write sorted/indented JSON, then run:

```powershell
cd web
corepack pnpm run generate-api:namespace-analytics
```

The script must export JSON through Python and run `openapi-typescript` against that JSON. Do not hand-edit either generated file.

- [ ] **Step 6: Commit route and generated contract**

```text
feat(analytics): expose namespace analytics API
```

## Task 4: Integrate Canonical Subpath Baseline

**Files:** shared branch integration only; do not manually reproduce its runtime-config changes.

- [ ] **Step 1: Verify the subpath branch has a committed implementation**

Run from the repository root:

```powershell
git log --oneline dev..codex/subpath-deployment
git -c safe.directory='C:/Users/USER/projects/skillhub/.worktrees/subpath-deployment' -C '.worktrees/subpath-deployment' status --short --branch
```

Success criterion: the branch ref contains the subpath implementation commit and its worktree no longer holds that implementation only as uncommitted files.

- [ ] **Step 2: Merge the branch without editing its worktree**

```powershell
git merge --no-edit codex/subpath-deployment
```

Resolve only genuine conflicts in analytics-owned documentation or frontend route/menu files. Preserve the subpath branch's `getAppBasePath`, `buildApiUrl`, router `basepath`, runtime config, and production Playwright harness verbatim unless an analytics test proves an integration defect.

- [ ] **Step 3: Run subpath baseline tests**

```powershell
cd web
corepack pnpm test -- src/shared/lib/runtime-config.test.ts src/app/router.test.ts src/api/client.test.ts
corepack pnpm exec playwright test --config=playwright.subpath.config.ts
```

Expected: the existing subpath unit tests and three production-bundle scenarios pass before analytics UI work begins.

## Task 5: Typed Frontend API, Search State, And Query Hook

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`
- Create: `web/src/features/admin/namespace-analytics-search.ts`
- Create: `web/src/features/admin/namespace-analytics-search.test.ts`
- Create: `web/src/features/admin/use-namespace-analytics.ts`
- Create: `web/src/features/admin/use-namespace-analytics.test.ts`

- [ ] **Step 1: Write failing URL, period, and API tests**

Assert the default search state is `ALL`, `ACTIVE`, `30d`, all sources, period downloads descending, page 0, size 20. Assert a fixed `now` resolves 7/30/90-day UTC instants. Assert API serialization emits camelCase parameters and passes the logical endpoint to the shared base-aware fetch layer.

```typescript
expect(resolveAnalyticsPeriod({ period: '30d' }, new Date('2026-08-04T00:00:00Z'))).toEqual({
  startTime: '2026-07-05T00:00:00.000Z',
  endTime: '2026-08-04T00:00:00.000Z',
})
```

- [ ] **Step 2: Run focused Vitest and verify RED**

```powershell
cd web
corepack pnpm test -- src/api/client.test.ts src/features/admin/namespace-analytics-search.test.ts src/features/admin/use-namespace-analytics.test.ts
```

Expected: imports/exports are missing.

- [ ] **Step 3: Implement strict generated aliases, serializers, and hook**

Import `components` from `./generated/namespace-analytics-schema`. Define aliases from generated schemas rather than handwritten response shapes. Add `adminApi.getNamespaceAnalytics(params)` and a `useQuery` hook keyed by `['admin', 'namespace-analytics', params]`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: all URL/search/client/hook tests pass.

- [ ] **Step 5: Commit the frontend data slice**

```text
feat(analytics): add namespace analytics data client
```

## Task 6: Approved Namespace Analytics Page

**Files:**
- Create: `web/src/pages/admin/namespace-analytics.tsx`
- Create: `web/src/pages/admin/namespace-analytics.test.tsx`

- [ ] **Step 1: Write failing component tests**

Mock the query hook and router navigation. Cover five summary cards, the `GLOBAL` badge, zero values, default sorting, filter changes resetting page, loading skeleton, empty/clear action, error/retry action, page sizes, and the `View events` destination with explicit start/end/source.

- [ ] **Step 2: Run page test and verify RED**

```powershell
cd web
corepack pnpm test -- src/pages/admin/namespace-analytics.test.tsx
```

Expected: module missing.

- [ ] **Step 3: Implement the approved summary-first page**

Compose existing `Card`, `Input`, `Select`, `Button`, `Table`, and badge primitives. Render five totals above one consolidated filter card and the namespace table. Use `useSearch` plus `navigate({ search: ... })`; do not fetch with `useEffect`, call `window.location`, or hard-code `/skillhub`.

The row action must be:

```typescript
navigate({
  to: '/admin/download-events',
  search: {
    namespace: item.slug,
    startTime: period.startTime,
    endTime: period.endTime,
    source: period.source ?? undefined,
  },
})
```

- [ ] **Step 4: Run page tests and verify GREEN**

Expected: all page state and rendering tests pass.

- [ ] **Step 5: Commit the page slice**

```text
feat(analytics): build namespace analytics dashboard
```

## Task 7: Router, Menu, Download Drill-Down, And Localization

**Files:**
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/router.test.ts`
- Modify: `web/src/shared/components/user-menu.tsx`
- Modify: `web/src/shared/components/user-menu.test.tsx`
- Modify: `web/src/pages/admin/download-events.tsx`
- Modify: `web/src/pages/admin/download-events.test.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [ ] **Step 1: Write failing route/menu/drill-down tests**

Assert `/admin/namespace-analytics` is registered and `SUPER_ADMIN`-protected; the menu key appears only for super admins; Download Events initializes namespace/start/end/source from its validated router search; and all three locale files contain the complete `namespaceAnalytics` keys.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
cd web
corepack pnpm test -- src/app/router.test.ts src/shared/components/user-menu.test.tsx src/pages/admin/download-events.test.tsx src/i18n/zh-tw-locale.test.ts
```

- [ ] **Step 3: Implement logical route and localized navigation**

Add the route through TanStack Router only. Preserve the shared router `basepath` from Task 4. Initialize Download Events local filter state from `useSearch({ from: '/admin/download-events' })`, converting ISO instants with `toLocalDateTimeInputValue`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: route, role, locale, and incoming-filter tests pass.

- [ ] **Step 5: Commit the integration slice**

```text
feat(analytics): link namespace analytics workflow
```

## Task 8: Subpath Production E2E And Route Documentation

**Files:**
- Modify: `web/e2e/subpath-deployment.spec.ts`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `server-python/tests/test_route_registry.py`

- [ ] **Step 1: Write the failing production-bundle scenario**

Extend the mock API with a `SUPER_ADMIN` analytics response. Navigate directly to `/skillhub/admin/namespace-analytics`, reload, observe `/skillhub/api/v1/admin/namespace-analytics`, change a filter without losing the prefix, click `View events`, and assert `/skillhub/admin/download-events` contains namespace/startTime/endTime/source. Keep `observed.apiRootEscapes` empty.

- [ ] **Step 2: Run Playwright and verify RED**

```powershell
cd web
corepack pnpm exec playwright test --config=playwright.subpath.config.ts -g "namespace analytics"
```

Expected: the scenario fails until route/API/drill-down integration is present in the production bundle.

- [ ] **Step 3: Complete only the integration required by the failing scenario**

Do not alter ingress, OAuth, cookies, or runtime config. Fix analytics-owned route/API/navigation code only.

- [ ] **Step 4: Verify E2E GREEN and route registry**

Run the focused Playwright command and:

```powershell
cd ..\server-python
uv --no-cache run pytest tests/test_route_registry.py -q
```

- [ ] **Step 5: Commit E2E and docs**

```text
test(analytics): verify namespace analytics subpath flow
```

## Task 9: Full Verification, Result Record, And Acceptance Handoff

**Files:**
- Create: `docs/backend-python-maintenance/results/2026-08-04-namespace-analytics.md`

- [ ] **Step 1: Run backend verification**

```powershell
cd server-python
uv --no-cache run pytest tests -q
uv --no-cache run python -m compileall app
```

- [ ] **Step 2: Run frontend and generated-contract verification**

```powershell
cd ..\web
corepack pnpm run generate-api:namespace-analytics
git diff --exit-code -- src/api/generated/namespace-analytics-openapi.json src/api/generated/namespace-analytics-schema.d.ts
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm test
corepack pnpm run build
corepack pnpm exec playwright test --config=playwright.subpath.config.ts
```

- [ ] **Step 3: Run repository checks**

```powershell
cd ..
git diff --check
git status --short
```

Inspect the intended diff for Python-only boundaries, no migration, no hard-coded `/skillhub`, no browser-root admin navigation, and no unrelated files.

- [ ] **Step 4: Record exact verification evidence**

Write the commands, exit codes, test counts, existing warnings, branch/commit list, acceptance URL, and any organization-runtime gate to the result document. Do not claim production TLS/Keycloak verification from local evidence.

- [ ] **Step 5: Commit the result document and final reviewed diff**

```text
docs(analytics): record namespace analytics verification
```

- [ ] **Step 6: Hand off for user acceptance**

Provide the isolated worktree path, feature branch, logical and `/skillhub` URLs, metric semantics, exact verification counts, result-document path, and any remaining external-only gate. Do not push or open a PR unless the user explicitly requests it.
