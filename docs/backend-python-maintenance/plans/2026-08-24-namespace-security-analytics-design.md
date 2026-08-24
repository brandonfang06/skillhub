# Namespace Security Analytics Design

**Date:** 2026-08-24
**Status:** Approved for implementation

## Goal

Give platform super administrators one namespace-oriented view of security
findings across the whole SkillHub inventory, including non-public and
non-catalog content that ordinary discovery pages do not expose.

This is a security inventory, not an extension of the catalog eligibility
metric. It includes retained skills and versions regardless of:

- namespace status: `ACTIVE`, `FROZEN`, or `ARCHIVED`;
- skill container status: `ACTIVE` or `ARCHIVED`;
- platform-hidden overlay;
- visibility: `PUBLIC`, `NAMESPACE_ONLY`, or `PRIVATE`; and
- version status: `DRAFT`, `SCANNING`, `SCAN_FAILED`, `UPLOADED`,
  `PENDING_REVIEW`, `PUBLISHED`, `REJECTED`, or `YANKED`.

Deleted versions and soft-deleted audit records are excluded.

## Recommended Page Structure

Keep `/admin/namespace-analytics` and add two URL-backed views:

- **Catalog & adoption**: the existing maintainer, skill, and download view;
- **Security risks**: the new cross-namespace security inventory.

Do not combine catalog and security columns in one table. Their inclusion
rules intentionally differ: catalog analytics counts currently usable
published skills, while security analytics must include private, hidden,
unpublished, rejected, yanked, and archived inventory.

The security view contains:

1. Summary metrics for affected namespaces, distinct affected skills,
   distinct affected versions, and total finding instances.
2. A clickable distribution of finding instances using `CRITICAL`, `HIGH`,
   `MEDIUM`, `LOW`, `INFO`, and `UNCLASSIFIED`.
3. A namespace table with affected skills, affected versions, highest
   severity, finding-instance severity distribution, total findings, and
   latest scan time.
4. Expandable namespace rows that lazily load affected skills.
5. A skill/version detail drawer that shows lifecycle and visibility badges,
   scanner information, scan state, and the existing finding detail UI.

Default ordering is highest risk first: critical, high, medium, total
findings, most recent scan, then namespace slug.

## Snapshot Semantics

Security findings are version-scoped. For each retained skill version and
scanner type, use only the latest active (`deleted_at IS NULL`) audit record.
An affected version has at least one finding in that snapshot. An affected
skill or namespace has at least one affected descendant version.

The same finding reported by different scanners remains two finding instances;
the current data model has no stable cross-scanner deduplication key.

The dashboard says **detected findings**, not **open findings**. Individual
findings are JSON records and do not currently have resolved or closed state.
A newer scan supersedes an older scan for the same version and scanner type.

If `findings_count` is positive but severity cannot be classified, preserve it
under `UNCLASSIFIED` instead of silently dropping it.

## Filters

All status and visibility filters default to `ALL`. Primary filters are
namespace or skill search, severity, visibility, and version status. Secondary
filters are namespace type/status, skill status, platform-hidden state, and
scanner type.

There is no default date range. Old findings remain visible until a newer scan
for the same version and scanner supersedes them or the audit is soft-deleted.
The table displays the latest scan time so administrators can judge staleness.

## Access And Disclosure

- Browser-session `SUPER_ADMIN` only.
- Reject bearer API tokens on aggregate admin routes.
- Do not expose code snippets in aggregate namespace or skill rows.
- Detailed finding content appears only after explicit drill-down.
- Do not route private/unpublished drill-down through public catalog discovery.

## API And Module Shape

- `GET /api/v1/admin/namespace-analytics/security` for summary and paginated
  namespace rows.
- `GET /api/v1/admin/namespace-analytics/security/namespaces/{namespaceId}/skills`
  for lazy, paginated affected-skill rows.
- Reuse the existing per-version security-audit endpoint for drawer detail
  where its response is sufficient.

Keep SQL in a focused Python repository/query module and generate the frontend
OpenAPI contract. Preserve root and `/skillhub` routing through the established
API client and TanStack Router search state.

## Verification Expectations

- Contract tests for every lifecycle, visibility, hidden, and namespace-status
  inclusion rule.
- PostgreSQL integration tests with real findings JSONB and multiple scan rounds
  and scanner types.
- Authorization tests for unauthenticated, non-admin, bearer-token, and
  `SUPER_ADMIN` requests.
- Frontend tests for default ALL coverage, filters, sorting, expansion, drawer,
  translations, pagination, reload, and empty/error states.
- Production-bundle browser verification at root and `/skillhub` with the real
  Python backend and PostgreSQL-connected service stack.

## Non-goals

- No finding-level remediation workflow or resolved/closed state.
- No scanner rerun, override, hide, yank, or delete action from this view.
- No schema migration or materialized rollup unless PostgreSQL evidence shows
  the live aggregate cannot meet an agreed performance target.
- No change to public catalog visibility or ordinary user access.
- No Java, Maven, Spring Boot, or hybrid runtime.
