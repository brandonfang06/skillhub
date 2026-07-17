# My Namespaces Filter Design

## Context

Organization deployments can have more than 60 product namespaces. The current
My Namespaces page renders every namespace card in one list with no way to
narrow the result, which makes routine administration slow.

The existing `useMyNamespaces()` query already returns the complete authorized
namespace collection. This scale does not require server-side filtering or
pagination.

## Goals

- Let users find namespaces by display name or slug.
- Let users filter namespaces by lifecycle status.
- Keep filtering immediate and entirely client-side.
- Preserve the existing namespace order, permissions, actions, and API.
- Provide localized controls and a clear no-match state.

## Non-Goals

- No Python backend or API contract changes.
- No database query or schema changes.
- No URL query parameters or persisted filter preferences.
- No role, ownership, dependency, or deletion-readiness filters.
- No sorting or pagination changes.

## User Experience

When at least one namespace exists, render a compact filter toolbar between the
page header and namespace grid.

The toolbar contains:

- A search input with a search icon and localized placeholder.
- A clear icon button when the search input is non-empty.
- A status select with `All`, `Active`, `Frozen`, and `Archived`.
- A localized result count showing matched and total namespaces.

The layout is one row on wider screens and wraps vertically on narrow screens.
Controls must retain stable dimensions and accessible labels.

If namespaces exist but no namespace matches the active filters, replace the
grid with a filter-specific empty state and a `Clear filters` action. This must
remain distinct from the existing empty state shown when the user has no
namespaces.

## Filtering Rules

Search normalization:

- Trim leading and trailing whitespace.
- Compare case-insensitively.
- Match against `displayName` and `slug`.
- Treat a leading `@` in the search query as optional so `@product-a` matches
  the `product-a` slug.

Status filtering:

- `ALL` accepts every status.
- `ACTIVE`, `FROZEN`, and `ARCHIVED` require an exact status match.

Search and status filters combine with logical AND. Filtering must not reorder
the collection returned by the backend.

## Frontend Design

Keep page-local state in `MyNamespacesPage`:

- `searchQuery`
- `statusFilter`

Extract the pure matching behavior into a small exported helper in the same
page module only if doing so improves direct testability. Do not introduce a
new shared abstraction for a single-page concern.

Derive filtered results during render. With approximately 60 namespaces,
memoization is optional and should only be used if it improves clarity.

Reuse existing shared controls:

- `Input`
- Radix-based `Select`
- `Button`
- Lucide `Search` and `X` icons
- `EmptyState`

All visible strings belong under the existing `myNamespaces` i18n namespace in
English, Simplified Chinese, and Traditional Chinese locale files.

## Compatibility And Maintenance

This feature changes only the My Namespaces page and its locale strings. It
does not alter generated OpenAPI files, backend routes, namespace response
types, permissions, or lifecycle behavior.

Keeping the feature page-local minimizes conflicts when following upstream
changes. If upstream later adds equivalent filtering, the local toolbar can be
removed without data migration or API cleanup.

## Testing

Add frontend tests covering:

- Case-insensitive display-name matching.
- Slug matching with and without a leading `@`.
- Exact status filtering.
- Combined search and status filtering.
- Preserving the input collection order.
- Rendering the filter-specific no-match state.
- Clearing active filters restores all namespace cards.
- Existing namespace actions remain visible and unchanged for matching cards.

Verification:

- Focused My Namespaces tests.
- Full frontend Vitest suite.
- TypeScript typecheck.
- ESLint.
- Production frontend build.
- Locale JSON parse.
- `git diff --check`.

## Acceptance Criteria

- A user can reduce a list of 60 or more namespaces by name, slug, or status
  without a network request.
- Search and status filters work together and update immediately.
- No-match and no-namespace states are clearly different.
- Existing namespace navigation, permissions, and lifecycle actions are
  unaffected.
- No backend, database, or generated API file changes are introduced.
