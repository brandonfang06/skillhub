# My Namespaces Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add immediate display-name/slug search and lifecycle-status filtering to the My Namespaces page without backend changes.

**Architecture:** Keep filter state and toolbar rendering page-local. Add one pure `filterManagedNamespaces` helper for deterministic matching tests, then derive the displayed cards from the existing `useMyNamespaces()` result.

**Tech Stack:** React 19, TypeScript, Radix Select, Lucide icons, i18next, Vitest, Testing Library

---

## File Structure

- Modify `web/src/pages/dashboard/my-namespaces.tsx`: filter types/helper, local state, toolbar, result count, no-match state.
- Modify `web/src/pages/dashboard/my-namespaces.test.ts`: pure filtering and UI behavior coverage.
- Modify `web/src/i18n/locales/en.json`: English filter copy.
- Modify `web/src/i18n/locales/zh.json`: Simplified Chinese filter copy.
- Modify `web/src/i18n/locales/zh-TW.json`: Traditional Chinese filter copy.

### Task 1: Pure Namespace Filtering

**Files:**
- Modify: `web/src/pages/dashboard/my-namespaces.test.ts`
- Modify: `web/src/pages/dashboard/my-namespaces.tsx`

- [x] **Step 1: Write failing helper tests**

Add tests that call:

```ts
filterManagedNamespaces(namespaces, { query: '@PRODUCT', status: 'ACTIVE' })
```

Assert that matching is case-insensitive, strips an optional leading `@`,
matches display name or slug, combines with exact status, and preserves input
order.

- [x] **Step 2: Verify the helper tests fail**

Run:

```powershell
cd web
.\node_modules\.bin\vitest.cmd run src/pages/dashboard/my-namespaces.test.ts
```

Expected: FAIL because `filterManagedNamespaces` is not exported.

- [x] **Step 3: Implement the minimal helper**

Add:

```ts
export type NamespaceStatusFilter = 'ALL' | 'ACTIVE' | 'FROZEN' | 'ARCHIVED'

export function filterManagedNamespaces(
  namespaces: ManagedNamespace[],
  filters: { query: string; status: NamespaceStatusFilter },
) {
  const normalizedQuery = filters.query.trim().replace(/^@/, '').toLowerCase()
  return namespaces.filter((namespace) => {
    const matchesQuery = normalizedQuery.length === 0
      || namespace.displayName.toLowerCase().includes(normalizedQuery)
      || namespace.slug.toLowerCase().includes(normalizedQuery)
    const matchesStatus = filters.status === 'ALL' || namespace.status === filters.status
    return matchesQuery && matchesStatus
  })
}
```

- [x] **Step 4: Verify helper tests pass**

Run the focused Vitest command and expect all My Namespaces tests to pass.

### Task 2: Filter Toolbar And No-Match State

**Files:**
- Modify: `web/src/pages/dashboard/my-namespaces.test.ts`
- Modify: `web/src/pages/dashboard/my-namespaces.tsx`

- [x] **Step 1: Write failing UI tests**

Render multiple namespaces and use Testing Library to:

- type a display-name/slug query and assert only matching cards remain;
- select an archived status and assert query and status combine;
- assert matched/total count text is rendered;
- assert the no-match state is distinct from the no-namespace state;
- click `Clear filters` and assert all cards return.

- [x] **Step 2: Verify UI tests fail**

Run the focused My Namespaces test file. Expected: FAIL because the toolbar and
filter-specific empty state do not exist.

- [x] **Step 3: Implement the toolbar**

Import `Search` and `X`, `Input`, and the shared Select primitives. Add:

```ts
const [searchQuery, setSearchQuery] = useState('')
const [statusFilter, setStatusFilter] = useState<NamespaceStatusFilter>('ALL')
const filteredNamespaces = filterManagedNamespaces(namespaces ?? [], {
  query: searchQuery,
  status: statusFilter,
})
```

Render a responsive toolbar only when the original namespace collection is
non-empty. Give the input and status trigger localized accessible labels.
Render `filteredNamespaces` in the existing grid without changing card action
logic.

When `filteredNamespaces` is empty, render `EmptyState` with filter-specific
copy and a button that resets query to `''` and status to `ALL`.

- [x] **Step 4: Verify UI tests pass**

Run the focused test file and expect all tests to pass.

### Task 3: Localization And Full Verification

**Files:**
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [x] **Step 1: Add locale keys**

Add under `myNamespaces`:

```json
{
  "searchPlaceholder": "Search by name or @slug",
  "searchLabel": "Search namespaces",
  "clearSearch": "Clear namespace search",
  "statusFilterLabel": "Filter by status",
  "filterAll": "All statuses",
  "resultCount": "{{matched}} of {{total}} namespaces",
  "noMatchTitle": "No namespaces match these filters",
  "noMatchDescription": "Change the search or status filter and try again.",
  "clearFilters": "Clear filters"
}
```

Use equivalent Simplified and Traditional Chinese translations. Reuse existing
`namespaceStatus.active`, `namespaceStatus.frozen`, and
`namespaceStatus.archived` keys for status option labels.

- [x] **Step 2: Run full verification**

Run:

```powershell
cd web
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run build
```

Parse all three locale JSON files with Node and run `git diff --check`.

- [x] **Step 3: Review the final diff**

Confirm:

- no backend, generated API, schema, or lockfile changes;
- filter controls do not trigger network requests;
- namespace card actions and permissions remain unchanged;
- mobile layout wraps without fixed-width overflow.

Verification completed on 2026-07-17:

- focused My Namespaces tests: 14 passed;
- full frontend tests: 194 files and 685 tests passed;
- TypeScript typecheck and ESLint passed with zero warnings;
- production build passed with only the existing runtime-config and chunk-size warnings;
- locale JSON parsing and `git diff --check` passed.

- [x] **Step 4: Commit and push**

Stage only the plan, page, tests, and three locale files. Commit with:

```text
feat: filter managed namespaces
```

Push `codex/namespace-filter` to `origin`.
