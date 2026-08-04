# Platform Namespace Portfolio Analytics Design

**Status:** Ready for user review
**Date:** 2026-08-04

## Problem

A platform administrator needs one page that explains the scale and adoption of
the SkillHub catalog across namespaces: who maintains the catalog, how many
skills each namespace maintains, and how much those skills are downloaded.
The page must support filtering so an operator can move from an organization-
wide summary to a useful subset without inspecting raw download events.

## Existing Product Baseline

- `/admin/download-events` already exposes filterable, paginated raw download
  events for platform readers.
- `local_skill_download_event` records successful published-skill downloads and
  retains events according to `SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS`
  (12 months by default).
- `skill.download_count` stores the lifetime public counter for each skill.
- Namespace reads already expose namespace identity, lifecycle status, and
  dependency skill counts, but there is no platform-level namespace analytics
  rollup.
- The requested page is a summary/portfolio view, not a replacement for the raw
  download-event audit page.
- The in-progress `codex/subpath-deployment` worktree establishes
  `SKILLHUB_WEB_BASE_PATH=/skillhub`, a TanStack Router `basepath`, base-aware
  same-origin API URLs, and production-bundle subpath E2E coverage. That work is
  complete in its worktree but was not yet committed or merged when this design
  was updated.

## Initial Outcome

Provide a platform-admin page that can show one row per namespace with, at
minimum:

- namespace identity and lifecycle status;
- maintainer count, defined as the number of distinct owners who own at least
  one skill included by the current metric definition and filter set;
- skill count per namespace;
- lifetime downloads, summed from eligible skills' `skill.download_count`;
- period downloads, summed from eligible skills' retained
  `local_skill_download_event` rows within the selected date range;
- filters and deterministic sorting;
- organization-wide maintainer, skill, and download totals that reflect the
  active filter set. The organization-wide maintainer total must de-duplicate
  the same owner across namespaces rather than summing row-level maintainer
  counts.

## Metric Semantics

### Eligible skill

An eligible skill satisfies all of these conditions:

- the skill container is `ACTIVE`;
- the platform `hidden` overlay is false;
- at least one version is `PUBLISHED`.

The default namespace population is `GLOBAL` plus active team namespaces. When
the operator selects frozen or archived namespaces, the same skill-level rules
apply so the page can show their retained catalog history without describing
those rows as currently distributable.

### Maintainers

`maintainerCount` is the count of distinct `skill.owner_id` values among
eligible skills. Row-level counts are de-duplicated inside each namespace. The
summary count is de-duplicated across all namespaces matching the current
namespace filters, so one person who owns skills in two namespaces contributes
one to the organization-wide total.

### Skills

`skillCount` counts eligible skill containers, not versions. Every skill belongs
to one namespace, so the summary total counts the eligible skill IDs across all
matching namespace rows without summing version records.

### Downloads

- `lifetimeDownloads` sums `skill.download_count` for eligible skills.
- `periodDownloads` counts retained `local_skill_download_event` rows for
  eligible skill IDs where `startTime <= created_at <= endTime`, matching the
  existing Download Events filter contract.
- The default period is the previous 30 days ending at the current time.
- Date and source filters affect only `periodDownloads`. Namespace search,
  type, status, and eligibility affect both lifetime and period metrics.
- Period values describe retained analytics data. The UI must state that
  retention is controlled by `SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS`
  and must not present period data as all-time history.

## Constraints

- Preserve the full-Python backend and Python-owned schema.
- Keep organization-specific event analytics isolated from upstream-followed
  schema unless an equivalent upstream contract appears.
- Restrict the portfolio view to the appropriate platform-admin boundary.
- Aggregate server-side; do not fetch raw event pages and sum them in the
  browser.
- Follow existing React, TanStack Query, generated API, localization, and
  admin-route patterns.
- Preserve root and subpath deployments. Browser navigation, API calls, deep
  links, reloads, and drill-down URLs must work with an empty base path and with
  `/skillhub` without duplicating or escaping the prefix.

## Considered Approaches

### 1. Server-side live aggregation (selected)

Build the eligible-skill set once per request, aggregate core skill ownership
and lifetime counters by namespace, aggregate retained period events by skill,
then join the two rollups. Apply filters, summary aggregation, deterministic
sort, and pagination in the backend.

This is the smallest accurate design. It keeps the browser response bounded,
uses the current source-of-truth counters and event table, and avoids a new
refresh pipeline. Existing event indexes support skill/time and namespace/time
access; representative `EXPLAIN` evidence should decide whether another index
is necessary.

### 2. Persisted rollup or materialized view

Maintain periodic namespace totals in a new local table or materialized view.
Reads would be fast at large scale, but values become stale and the first
release would need a refresh scheduler, failure recovery, backfill, and another
organization-specific schema lifecycle. Defer until measured query latency
shows that live aggregation is insufficient.

### 3. Browser aggregation over existing event pages

Fetch namespaces and raw download-event pages, then aggregate in React. This
would produce incorrect totals once pagination or the CSV cap is reached, move
high-volume work to the browser, and cannot efficiently calculate lifetime
counts. Reject this approach.

## User Experience

### Navigation and page

- Add a `Namespace Analytics` item to the platform-admin menu.
- Add the protected logical route `/admin/namespace-analytics`. TanStack Router
  applies the configured application base path, so its public URL is
  `${basePath}/admin/namespace-analytics` and becomes
  `/skillhub/admin/namespace-analytics` in the canonical deployment.
- Keep `/admin/download-events` as the raw-event investigation page.
- Restrict page navigation and its API to `SUPER_ADMIN` for the first release.

### Summary strip

Show five totals for the complete filtered result set, not only the visible
page:

1. Namespaces
2. Maintainers
3. Catalog Skills
4. Lifetime Downloads
5. Downloads in the selected period

The period card includes the selected range label, such as `Last 30 days`.

### Filters

- namespace name or slug search;
- namespace type: `All`, `Team`, `Global`;
- namespace status: `All`, `Active`, `Frozen`, `Archived`;
- period preset: `Last 7 days`, `Last 30 days`, `Last 90 days`, `Custom`;
- period download source: `All`, `Web`, `CLI`, `API`;
- clear filters.

Defaults are all namespace types, active status, last 30 days, and all download
sources. Search is trimmed and case-insensitive. Changing a filter resets the
table to page zero.

### Namespace table

Each row shows:

- namespace display name and `@slug`;
- `GLOBAL` or `TEAM` badge;
- namespace status;
- distinct maintainers;
- eligible skills;
- lifetime downloads;
- period downloads;
- `View events` action.

All metric columns and namespace name are sortable. The default is period
downloads descending, then lifetime downloads descending, skill count
descending, and namespace slug ascending. The API must add a unique namespace
ID or slug tie-breaker to every sort. Use server-side pagination with page sizes
20, 50, and 100.

`View events` uses TanStack Router navigation to the logical
`/admin/download-events` route with namespace, selected start/end, and selected
source encoded as search parameters. The router must supply the configured base
path; the feature must not construct a browser-root `/admin/...` URL. The
Download Events page must initialize its controls from those search parameters
so the drill-down is reproducible and shareable.

### States

- Loading: summary and table skeletons.
- Empty: explain that no namespaces match the current filters and offer Clear
  filters.
- Error: preserve the selected filters and show a retry action.
- Zero metrics: display `0`, not a dash.
- Historical namespace: retain its actual status badge and avoid calling its
  skills currently available.

Charts are not part of the first release. A sortable table is more accurate for
comparing many namespaces and supports exact operational drill-down.

## Backend And API Design

### Endpoint

Add:

```text
GET /api/v1/admin/namespace-analytics
```

Query parameters:

- `query`
- `namespaceType=ALL|TEAM|GLOBAL`
- `namespaceStatus=ALL|ACTIVE|FROZEN|ARCHIVED`
- `startTime`
- `endTime`
- `source=web|cli|api`
- `sort=namespace|maintainers|skills|lifetimeDownloads|periodDownloads`
- `direction=asc|desc`
- `page` and `size`

The route validates the time range, enum-like filters, sort key, direction, and
page bounds at the transport boundary. It rejects bearer API tokens on the
admin browser surface, resolves the authenticated session, requires
`SUPER_ADMIN`, calls a dedicated repository, and returns the established
success envelope and request ID.

### Response data

The response data contains:

```text
summary:
  namespaceCount
  maintainerCount
  skillCount
  lifetimeDownloads
  periodDownloads
period:
  startTime
  endTime
  source
  retentionMonths
items[]:
  namespaceId
  slug
  displayName
  type
  status
  maintainerCount
  skillCount
  lifetimeDownloads
  periodDownloads
page
size
total
```

Use integer/big-integer-safe values consistently with existing frontend API
contracts. The summary is calculated independently of pagination but with the
same namespace filters and eligible-skill definition.

### Module boundaries

- Route: `server-python/app/api/namespace_analytics.py`.
- SQL and row projection: a dedicated namespace-analytics repository under
  `server-python/app/`.
- Do not add aggregation SQL to the route handler.
- Do not add a schema migration for the live-aggregation release.
- Keep `local_skill_download_event` and its retention behavior unchanged.

Use one eligible-skill relation for summary and rows so the maintainer, skill,
and download metrics cannot drift apart. Count period events by `skill_id`, not
by parsing display coordinates. Deleted skills already cascade their local
event rows under the current schema contract. Begin from the filtered namespace
set and left-join the metric rollups so namespaces with zero eligible skills
remain visible with zero-valued metrics.

## Frontend Design

- Page: `web/src/pages/admin/namespace-analytics.tsx`.
- Query feature: `web/src/features/admin/use-namespace-analytics.ts` using
  TanStack Query; no `useEffect` data fetch.
- API: add the typed client contract through generated OpenAPI types; do not
  hand-edit generated files.
- Router and platform-admin menu follow the current Download Events patterns.
- Use the shared `buildApiUrl`/runtime-config contract from the subpath work for
  every request. The backend endpoint remains logically
  `/api/v1/admin/namespace-analytics`; its public same-origin request inherits
  the configured base path.
- Filters remain URL search parameters so refresh, back/forward navigation, and
  shared drill-down URLs preserve state.
- Use TanStack `Link`/`navigate` for page and drill-down navigation. Do not use
  `window.location`, hard-code `/skillhub`, or concatenate a browser-root
  `/admin/...` URL.
- Add English, Simplified Chinese, and Traditional Chinese translation keys.
- Reuse existing Card, Input, Select, Table, Button, badge, pagination, date,
  and number-formatting patterns before creating any new shared component.

The current generic `generate-api` command still targets `/v3/api-docs`, while
FastAPI exposes `/openapi.json`. Implementation must establish a focused,
repeatable FastAPI OpenAPI export/generation path for this contract or repair
the generic path without manually editing generated output. Broad unrelated
generated-schema churn is outside this feature.

## Subpath Compatibility And Integration Order

The namespace analytics implementation must begin only after the
`codex/subpath-deployment` changes are committed and integrated into the feature
branch. Rebase or merge that baseline before editing overlapping frontend files,
especially the router, API client, platform-admin menu, runtime configuration,
and production Playwright suite. Do not copy or create a second base-path
mechanism inside this feature.

The contract is:

- application routes remain logical root-relative paths inside TanStack Router;
- the configured router `basepath` produces `/skillhub/...` browser URLs;
- `buildApiUrl` produces `/skillhub/api/...` same-origin requests when no
  separate API origin is configured;
- the ingress may strip `/skillhub` before forwarding, so backend route
  declarations remain `/api/...` and do not include the public prefix;
- a direct refresh of `/skillhub/admin/namespace-analytics` must resolve the SPA
  and reload its data without a root-path escape;
- `View events` must stay under `/skillhub/admin/download-events` and preserve
  encoded namespace, date, and source search parameters.

If the subpath branch changes these shared contracts before merge, follow its
merged helpers and tests rather than the provisional filenames in this design.

## Verification Design

Develop test-first at the API and UI seams.

Backend coverage:

- eligible versus archived, hidden, draft-only, rejected-only, private-only,
  yanked-only, and published skills;
- distinct owner counts per namespace and across the summary;
- skill containers counted once across multiple published versions;
- lifetime counter sums and inclusive period start/end boundaries;
- source, search, type, status, date, sort, direction, and pagination behavior;
- `GLOBAL`, active team, frozen, archived, empty, and zero-metric namespaces;
- summary totals use all filtered rows rather than the current page;
- unauthenticated, non-super-admin, bearer-token, and `SUPER_ADMIN` route cases;
- success envelope and request-id behavior;
- representative PostgreSQL query-plan inspection before adding any new index.

Frontend coverage:

- default filters and period-download sort;
- URL-backed filter parsing and page reset;
- summary cards, zero values, status/type badges, sorting, pagination, loading,
  empty, retry, and retention note;
- `View events` produces the correct namespace/date/source URL;
- Download Events consumes incoming URL filters;
- menu and route visibility for `SUPER_ADMIN` versus other users;
- English, Simplified Chinese, and Traditional Chinese rendering;
- desktop and narrow viewport smoke coverage.

Subpath production-bundle coverage extends the existing subpath Playwright suite
to verify:

- direct navigation and reload at
  `/skillhub/admin/namespace-analytics` render the protected page;
- the request is sent to
  `/skillhub/api/v1/admin/namespace-analytics`, with no `/api/...` root escape;
- changing filters preserves the `/skillhub` prefix and URL search state;
- `View events` reaches `/skillhub/admin/download-events` with the selected
  namespace, date range, and source; and
- the same analytics route still works for a root deployment with an empty base
  path.

Required implementation verification includes focused backend/frontend tests,
the full backend suite, frontend typecheck/lint/test/build, an authenticated
browser smoke path, generated API drift validation, and `git diff --check`.

## Non-Goals

- No charts, sparklines, trend comparison, or forecasting in the first release.
- No persisted rollup table, materialized view, scheduled aggregation job, or
  new schema migration without measured performance evidence.
- No unique-downloader metric; anonymous downloads cannot support a reliable
  people count without a separate privacy design.
- No maintainer identity list or per-maintainer leaderboard.
- No rollup CSV export; raw filtered event CSV remains available through
  Download Events.
- No changes to download recording, retention, public counters, namespace
  lifecycle, or skill lifecycle transitions.
- No `SKILL_ADMIN` or `AUDITOR` access expansion in the first release.
- No analytics-specific base-path, proxy, ingress, OAuth, cookie, or runtime
  configuration mechanism; this feature consumes the shared subpath contract.
- No Java, Maven, Spring Boot, or hybrid backend work.

## Decisions

- 2026-08-04: Use Superpowers brainstorming as the design workflow and keep Matt
  Pocock's overlapping interview flow inactive for this discussion.
- 2026-08-04: Visual companion accepted for layout comparisons.
- 2026-08-04: A maintainer is a distinct owner of at least one skill included
  by the current metric definition and filters. Show both per-namespace skill
  counts and a de-duplicated organization-wide skill total for the filtered
  result set.
- 2026-08-04: Count only currently usable catalog skills: the skill container
  is `ACTIVE`, the platform `hidden` overlay is false, and at least one version
  is `PUBLISHED`. Apply this same eligible-skill set to maintainer and download
  rollups so the page's metrics describe one coherent catalog population.
- 2026-08-04: Show both lifetime and period download totals. Lifetime totals
  sum `skill.download_count`; period totals sum retained download events for
  eligible skills. The period defaults to the last 30 days, and changing the
  date filter does not change lifetime totals.
- 2026-08-04: Include the `GLOBAL` namespace by default as a visually distinct
  row. Provide a namespace-type filter with `All`, `Team`, and `Global`; the
  default all-platform totals include both team and global catalog skills.
- 2026-08-04: Default the page to active team namespaces plus `GLOBAL`. Provide
  a namespace-status filter with `All`, `Active`, `Frozen`, and `Archived`.
  When historical statuses are selected, retain their eligible skill-owner and
  lifetime-download history; period downloads remain derived from actual event
  rows and are never synthesized or rewritten.
- 2026-08-04: Add a dedicated `/admin/namespace-analytics` page and admin-menu
  entry. Keep `/admin/download-events` as the raw investigation surface. Each
  namespace rollup row can drill into Download Events with the namespace and
  selected date range pre-applied.
- 2026-08-04: Default sorting is period downloads descending, then lifetime
  downloads descending, skill count descending, and namespace slug ascending.
- 2026-08-04: The user delegated remaining design-level choices to the
  recommended option. Select live server-side aggregation, a table-first UI,
  URL-backed filters, `SUPER_ADMIN`-only access, and no first-release charts or
  rollup persistence.
- 2026-08-04: Account for the in-progress canonical `/skillhub` deployment by
  keeping analytics routes logical and base-path-aware. Integrate the subpath
  branch before feature implementation, use its shared router/API helpers, and
  require production-bundle coverage for direct refresh, API traffic, filters,
  and the Download Events drill-down under `/skillhub`.
