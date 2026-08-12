# Search Namespace Filter Verification

Date: 2026-08-12

## Scope

- Added a single-select namespace filter to the authenticated home page, anonymous landing page, and Search page.
- Kept the existing `@namespace query` input syntax; an explicitly typed namespace takes precedence over the picker.
- Added a bounded server-side namespace candidate endpoint so deployments with 100+ namespaces do not load every namespace into the browser.
- Candidate visibility matches skill search: anonymous users see public skills, while authenticated namespace members may also see namespace-only skills.
- Preserved the selected namespace independently in the Search URL and retained the existing keyword, label, sort, starred, and pagination behavior.

## Automated Verification

- Focused backend search and route tests: 18 passed.
- Full backend suite: 1,315 passed, 17 skipped, 1 existing Starlette deprecation warning.
- Full frontend suite: 214 test files, 859 tests passed.
- TypeScript no-emit check: passed.
- ESLint with zero warnings: passed.
- Production build: passed with 2,402 modules transformed.
- Playwright against the current FastAPI service and real PostgreSQL/Redis: 2 passed.
  - Authenticated flow searched a simulated 125-namespace candidate set, selected a namespace, preserved it through navigation and reload, and stayed within a 390 x 844 viewport.
  - Anonymous landing flow selected a public namespace and carried it with the keyword into Search.
- The unmocked candidate endpoint executed against local PostgreSQL and returned `global` with 10 visible skills.

## Review Notes

- Included the authenticated user ID in the TanStack Query cache key to prevent namespace-only candidate data from being reused across login changes.
- Preserved the selected namespace display label when a later candidate query no longer contains the selected item.
- Added working ArrowUp/ArrowDown focus movement from the picker search field.
- Aligned namespace lifecycle filtering with skill search so read-only `FROZEN` namespaces remain searchable while `ARCHIVED` namespaces are excluded.
- The endpoint returns at most 50 candidates and the UI requests 20; users search display names or slugs instead of loading every namespace.

The verified change was held before integration until explicit commit and push approval.
