# Namespace Analytics CSV Export Design

**Status:** Approved
**Date:** 2026-08-09

## Problem

Platform administrators can filter and compare namespace portfolio analytics in
the browser, but cannot export the resulting dataset for report preparation or
further analysis. Copying the paginated table is incomplete and error-prone.

## Outcome

Add a CSV export to Namespace Analytics that downloads every namespace matching
the current filters and sort order, independently of the visible page, up to a
hard limit of 10,000 rows. The file must open correctly in Windows Excel and
remain safe when cells contain spreadsheet formula prefixes.

## Selected Approach

Generate the CSV in the Python backend from the same filtered namespace metric
relation used by the paginated analytics endpoint. The frontend performs an
authenticated same-origin fetch, saves the response as a file, and shows an
explicit warning when the backend reports that more than 10,000 rows matched.

This approach is selected because it keeps report data consistent with the
screen, avoids browser-side aggregation over a partial page, requires no new
runtime dependency, and preserves root and `/skillhub` deployments through the
shared API base URL contract.

## API Contract

Add:

```text
GET /api/v1/admin/namespace-analytics.csv
```

The endpoint accepts the same data-selection parameters as the JSON endpoint:

- `query`
- `namespaceType=ALL|TEAM|GLOBAL`
- `namespaceStatus=ALL|ACTIVE|FROZEN|ARCHIVED`
- `startTime`
- `endTime`
- `source=web|cli|api`
- `sort=namespace|maintainers|skills|lifetimeDownloads|periodDownloads`
- `direction=asc|desc`

It does not accept or apply `page` or `size`. Export ordering must match the
screen's deterministic sort, including the existing slug tie-breaker.

The route uses the same browser-admin boundary as Namespace Analytics:

- reject unauthenticated requests;
- reject users without `SUPER_ADMIN`;
- reject bearer API tokens on the browser-admin surface;
- preserve established error details for invalid filters and time ranges.

Successful responses use `text/csv; charset=utf-8` and include:

```text
Content-Disposition: attachment; filename="skillhub-namespace-analytics.csv"
X-SkillHub-Export-Truncated: true|false
X-SkillHub-Export-Row-Limit: 10000
```

The repository reads at most 10,001 rows. The extra row is used only to detect
truncation and is never written to the file.

## CSV Shape

The file is a single rectangular table with one row per namespace. Column names
are stable English machine-friendly identifiers:

1. `namespace_id`
2. `namespace_slug`
3. `display_name`
4. `namespace_type`
5. `namespace_status`
6. `maintainer_count`
7. `skill_count`
8. `lifetime_downloads`
9. `period_downloads`
10. `period_start_time`
11. `period_end_time`
12. `source`

Time values use ISO 8601 UTC offsets. `source` is empty when all download
sources are included. Numeric metrics are emitted without display formatting so
Excel and analysis tools recognize them as numbers.

The response begins with a UTF-8 BOM so Traditional and Simplified Chinese
namespace names open correctly in Windows Excel. String cells beginning with
`=`, `+`, `-`, `@`, tab, or carriage return are prefixed with a single quote to
neutralize CSV formula injection. Standard CSV quoting handles commas, quotes,
and newlines.

## Backend Design

- Keep HTTP binding and response headers in
  `server-python/app/api/namespace_analytics.py`.
- Keep filtering, SQL, row projection, export limit enforcement, and CSV
  rendering in `server-python/app/namespace_analytics/repository.py`.
- Extract one internal normalization path shared by list and export operations
  so filters, period resolution, and sort allowlisting cannot drift.
- Reuse `COMMON_CTE_SQL` and the existing eligibility semantics. Do not change
  which namespaces, skills, maintainers, or downloads are counted.
- Run one bounded export query. Do not run the paginated summary query because
  the CSV does not contain summary cards.
- Do not add a schema migration, persisted rollup, background job, or new index
  without measured evidence that the bounded query is inadequate.

## Frontend Design

- Add a focused export module under `web/src/features/admin/` that serializes
  the current analytics filters without `page` and `size`, calls the base-aware
  API URL, validates the response, and saves the returned Blob.
- Add an `Export CSV` button beside `Clear filters` on the Namespace Analytics
  filter card.
- Disable the button and show progress while one export is running to prevent
  duplicate requests.
- Show an error toast if the request fails.
- Show a warning toast when `X-SkillHub-Export-Truncated` is `true`, stating
  that only the first 10,000 matching namespaces were exported.
- Keep all user-facing text in English, Simplified Chinese, and Traditional
  Chinese locale files.
- Use the configured API base URL. Never hard-code `/skillhub` or escape to a
  browser-root `/api` URL.

## Failure And Edge Cases

- Zero matches returns a valid BOM-prefixed CSV containing only the header row.
- Reversed dates and invalid enum-like values return the existing API errors;
  no partial file is downloaded.
- Network and non-2xx responses leave the page and selected filters intact.
- A second click during an active export does not issue another request.
- Truncation is visible in the UI after the file is saved and is also available
  to API clients through response headers.

## Verification

Backend tests must cover:

- all current filters and deterministic sorting being passed to the export SQL;
- no pagination offset and a `limit + 1` read;
- 10,000-row truncation behavior and headers;
- BOM, header order, ISO timestamps, CSV quoting, Chinese text, and formula
  neutralization;
- empty export;
- unauthenticated, unauthorized, bearer-token, and `SUPER_ADMIN` routes;
- a real PostgreSQL execution of the nullable-filter export query.

Frontend tests must cover:

- export URL includes current filters/sort and excludes `page`/`size`;
- root and `/skillhub` API base URL behavior;
- Blob download filename and object URL cleanup;
- loading/disabled state, error toast, and truncation warning;
- existing analytics filters, sort, pagination, and drill-down remain intact.

Final verification includes focused red/green tests, full backend tests,
frontend tests, typecheck, lint, production build, authenticated browser checks
at desktop and narrow viewports for root and `/skillhub`, and
`git diff --check`.

## Non-Goals

- No native `.xlsx` workbook, styling, charts, or multiple sheets.
- No export of only the visible page.
- No raw download-event rows; that remains the Download Events export.
- No analytics metric, retention, authorization, or database schema change.
- No scheduled report delivery or server-side file storage.

## Decisions

- 2026-08-09: Use backend-generated CSV rather than browser aggregation or a
  new Excel dependency.
- 2026-08-09: Export all rows matching current filters and sorting, independent
  of page state, with a hard 10,000-row maximum.
- 2026-08-09: Warn explicitly when the result is truncated rather than relying
  only on a response header.
