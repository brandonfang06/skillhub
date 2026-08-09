# Namespace Analytics CSV Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, base-path-aware CSV export containing all namespaces that match the current Namespace Analytics filters and sort, capped at 10,000 rows.

**Architecture:** Extend the existing read-only FastAPI analytics route and repository with a bounded CSV query that shares normalization and metric SQL with the paginated JSON query. Add a focused frontend export feature that downloads the Blob through the configured API base URL and reports errors or truncation through localized toasts.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy, PostgreSQL, pytest, React 19, TypeScript, TanStack Router/Query, Vitest, Playwright, `uv`, and pnpm.

---

## File Map

- Modify `server-python/app/namespace_analytics/repository.py`: shared query normalization, bounded export read, CSV rendering, Excel safety, and export metadata.
- Modify `server-python/app/api/namespace_analytics.py`: protected CSV route and download headers.
- Modify `server-python/tests/test_namespace_analytics.py`: repository, renderer, route, auth, header, and OpenAPI behavior.
- Modify `server-python/tests/test_namespace_analytics_postgres.py`: real PostgreSQL execution of the export query.
- Modify `server-python/scripts/export_namespace_analytics_openapi.py`: focused OpenAPI must include both analytics GET routes.
- Regenerate `web/src/api/generated/namespace-analytics-openapi.json` and `web/src/api/generated/namespace-analytics-schema.d.ts` through the existing generator.
- Create `web/src/features/admin/export-namespace-analytics.ts`: URL serialization, authenticated fetch, response metadata, and browser file save.
- Create `web/src/features/admin/export-namespace-analytics.test.ts`: URL, base path, file save, truncation, and error coverage.
- Modify `web/src/pages/admin/namespace-analytics.tsx`: export button, progress state, and localized notifications.
- Modify `web/src/pages/admin/namespace-analytics.test.tsx`: export interaction and regression coverage.
- Modify `web/src/i18n/locales/en.json`, `zh.json`, and `zh-TW.json`: export labels and messages.
- Modify `web/src/i18n/namespace-analytics-locale.test.ts`: locale completeness assertions.
- Modify an existing root/subpath Playwright analytics scenario if required to cover the new button without creating a second deployment harness.
- Create `docs/backend-python-maintenance/results/2026-08-09-namespace-analytics-csv-export.md`: final evidence and known limits.

## Task 1: Backend CSV Contract

- [ ] Add failing renderer tests to `server-python/tests/test_namespace_analytics.py` asserting a UTF-8 BOM, exact field order, Chinese text, CSV quoting, ISO timestamps, numeric cells, and neutralization of `=`, `+`, `-`, `@`, tab, and carriage-return prefixes.
- [ ] Run `cd server-python; uv run --frozen pytest tests/test_namespace_analytics.py -q` and confirm failure because the renderer and export constants do not exist.
- [ ] Add `NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT = 10_000`, stable field names, a private cell sanitizer, and `render_namespace_analytics_csv(items, period)` to the repository.
- [ ] Return a BOM-prefixed header-only file when `items` is empty.
- [ ] Rerun the focused backend test and confirm the renderer tests pass.

The renderer test data must include this representative item:

```python
item = {
    "namespaceId": 7,
    "slug": "platform,tools",
    "displayName": "=危險名稱",
    "type": "TEAM",
    "status": "ACTIVE",
    "maintainerCount": 2,
    "skillCount": 4,
    "lifetimeDownloads": 30,
    "periodDownloads": 8,
}
```

## Task 2: Shared Normalization And Bounded Export Query

- [ ] Add a failing repository test that calls the wished-for `export_namespace_analytics_csv` with all filters and asserts the query receives normalized values, the current allowlisted order, `limit=10001`, and no offset.
- [ ] Add a failing truncation test whose fake connection returns 10,001 rows and assert the result contains exactly 10,000 CSV records plus the header and reports `truncated=True`.
- [ ] Run the focused backend tests and confirm failure because the export function is absent.
- [ ] Extract the existing filter, period, source, sort, and direction normalization into an immutable internal query object used by both `list_namespace_analytics` and the export function.
- [ ] Build the export SELECT from `COMMON_CTE_SQL`, project the same namespace metrics, use `_order_sql`, and apply only `LIMIT :limit`.
- [ ] Have `export_namespace_analytics_csv` return `(csv_body, truncated)` and clamp any internal requested limit to the 10,000-row hard maximum.
- [ ] Rerun all namespace analytics backend tests and confirm list behavior remains unchanged while export tests pass.

The public repository signature is:

```python
async def export_namespace_analytics_csv(
    engine: Any,
    *,
    query: str | None,
    namespace_type: str,
    namespace_status: str,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    source: str | None,
    sort: str,
    direction: str,
    limit: int = NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT,
) -> tuple[str, bool]:
    ...
```

## Task 3: Protected CSV Route And OpenAPI

- [ ] Add failing route tests for successful `SUPER_ADMIN` export, unauthenticated `401`, non-super-admin `403`, bearer rejection, reversed dates, headers, media type, BOM, and filter forwarding.
- [ ] Run the focused tests and confirm `GET /api/v1/admin/namespace-analytics.csv` returns `404`.
- [ ] Add the route beside the JSON route, reusing `reject_bearer_api_token_for_admin_route`, `resolve_current_user_or_401`, and `require_platform_role` in the same order.
- [ ] Return a FastAPI `Response` with filename, truncation, and row-limit headers.
- [ ] Update focused OpenAPI expectations so both `/api/v1/admin/namespace-analytics` and `/api/v1/admin/namespace-analytics.csv` are generated.
- [ ] Run `cd web; corepack pnpm run generate-api:namespace-analytics` and inspect that generated output changes only for the CSV route.
- [ ] Rerun backend route and focused OpenAPI tests and confirm they pass.

## Task 4: Real PostgreSQL Verification

- [ ] Extend `server-python/tests/test_namespace_analytics_postgres.py` with a test that calls the export function using nullable filters and verifies a BOM-prefixed CSV is returned without SQL type errors.
- [ ] Start or reuse the repository's PostgreSQL test service without changing deployment configuration.
- [ ] Run the PostgreSQL test with `SKILLHUB_TEST_DATABASE_URL` set to the real async PostgreSQL URL and confirm both list and export tests execute rather than skip.
- [ ] If the test reveals a query problem, add a focused failing regression case before changing production SQL.

## Task 5: Frontend Export Feature

- [ ] Create failing Vitest cases for `buildNamespaceAnalyticsCsvUrl(params)` asserting all current filters and sorting are present while `page` and `size` are absent.
- [ ] Add failing cases for root and `/skillhub` runtime API bases, a successful Blob result, filename fallback, truncation and row-limit header parsing, non-2xx responses, object URL cleanup, and link removal.
- [ ] Run `cd web; corepack pnpm test -- src/features/admin/export-namespace-analytics.test.ts` and confirm failure because the module is missing.
- [ ] Implement the focused module with strict result types, `buildApiUrl`, same-origin credentials, a non-2xx error, response-header parsing, Blob download, and immediate object URL cleanup after the click.
- [ ] Keep page state out of this feature and accept the already-resolved `NamespaceAnalyticsParams` object from the page.
- [ ] Rerun the focused feature tests and confirm they pass.

The feature result contract is:

```typescript
export interface NamespaceAnalyticsExportResult {
  truncated: boolean
  rowLimit: number
}
```

## Task 6: Page Interaction And Localization

- [ ] Add failing page tests asserting the export button uses current filters, becomes disabled while exporting, ignores a second click, reports failures, and shows a warning only when the export result is truncated.
- [ ] Run the page test and confirm the new assertions fail because no export control exists.
- [ ] Add a `Download` icon button beside Clear Filters, local `isExporting` state, and an async click handler calling the focused export feature.
- [ ] Add localized labels for export, progress, failure, success, and 10,000-row truncation in all three locale files.
- [ ] Extend locale tests to require each new key.
- [ ] Rerun focused page, feature, and locale tests and confirm they pass.

## Task 7: Regression And Runtime Verification

- [ ] Run `cd server-python; uv run --frozen pytest tests/test_namespace_analytics.py tests/test_namespace_analytics_postgres.py -q` with the PostgreSQL URL and record executed counts.
- [ ] Run `cd server-python; uv run --frozen pytest tests -q` and require zero failures.
- [ ] Run `cd web; corepack pnpm run typecheck`, `corepack pnpm run lint`, `corepack pnpm run test`, and `corepack pnpm run build` and require successful exits.
- [ ] Start the complete local runtime needed by the authenticated analytics page and verify a real CSV download using a `SUPER_ADMIN` session.
- [ ] Verify desktop and narrow viewports for both root and `/skillhub`, including filter persistence, disabled export state, saved file content, and no horizontal overflow.
- [ ] Confirm unauthenticated and non-super-admin users cannot export through direct API calls.
- [ ] Run `git diff --check` and inspect `git status --short` to ensure only planned files changed.
- [ ] Write exact commands, counts, browser scenarios, export headers, row limit, and any environment limitation to `docs/backend-python-maintenance/results/2026-08-09-namespace-analytics-csv-export.md`.
- [ ] Do not commit, merge, or push until the user separately requests it after reviewing the verified result.
