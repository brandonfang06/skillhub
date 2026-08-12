# Search Namespace Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-select, server-searchable namespace filter to home, landing, and Search pages without loading more than 20 of 100+ candidates at once.

**Architecture:** A new auth-aware read repository and transport-only FastAPI route expose namespaces that have at least one skill visible to the request identity. A Search feature hook and Radix dropdown query that endpoint and page containers synchronize the selected slug with the existing Search URL state and `@slug` parser.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, pytest, React 19, TanStack Query, Radix DropdownMenu, Vitest, Playwright.

## Execution Notes

- Repository SQL coverage was kept in `test_skill_search_namespaces.py`, then the
  same query was executed against the existing real PostgreSQL service. A broad
  100-namespace database seed was unnecessary because browser behavior is
  covered with 125 candidates and SQL visibility/lifecycle predicates are
  asserted directly.
- The existing web API OpenAPI response is a generic envelope rather than a
  generated item schema. Regenerating the full declaration produced unrelated
  repository-wide drift, so generated files were restored unchanged and the
  candidate contract was added to the existing manual API types module.
- Identity-aware query caching was reviewed after implementation and corrected
  before final verification.

---

## File Structure

- `server-python/app/skills/read_repository.py`: visibility-aligned searchable namespace SQL.
- `server-python/app/api/skills.py`: optional-auth candidate route and parameter bounds.
- `server-python/tests/test_skill_search_namespaces.py`: route contract and auth forwarding.
- `server-python/tests/test_skill_search_namespace_repository_postgres.py`: real PostgreSQL visibility and ranking checks.
- `web/src/api/generated/schema.d.ts`: regenerated OpenAPI contract.
- `web/src/api/types.ts`: generated-contract-derived candidate alias.
- `web/src/api/client.ts`: base-path-aware candidate request.
- `web/src/features/search/use-searchable-namespaces.ts`: TanStack Query hook and identity-aware key.
- `web/src/features/search/namespace-search-filter.tsx`: debounced server-search dropdown.
- `web/src/features/search/namespace-search-filter.test.tsx`: picker behavior coverage.
- `web/src/features/search/search-bar.tsx`: optional leading namespace control and responsive layout.
- `web/src/pages/home.tsx`: selected namespace state and navigation.
- `web/src/pages/landing.tsx`: use the shared search surface and selected namespace navigation.
- `web/src/pages/search.tsx`: URL-synchronized selected namespace and `@slug` compatibility.
- `web/src/i18n/locales/{en,zh,zh-TW}.json`: user-facing filter messages.
- `web/e2e/search-namespace-filter.spec.ts`: anonymous/authenticated desktop-mobile scenarios.
- `docs/backend-python-maintenance/results/2026-08-12-search-namespace-filter.md`: exact verification evidence.

### Task 1: Backend Repository And Route

**Files:**
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/app/api/skills.py`
- Create: `server-python/tests/test_skill_search_namespaces.py`
- Create: `server-python/tests/test_skill_search_namespace_repository_postgres.py`

- [ ] **Step 1: Write failing route tests**

Cover anonymous and authenticated requests, `q` trimming, default limit 20,
maximum limit 50, and the standard response envelope. Inject a repository
reader and assert it receives `query`, `limit`, and `current_user_id`.

- [ ] **Step 2: Run route tests and confirm RED**

Run:

```powershell
cd server-python
uv run --no-cache pytest tests/test_skill_search_namespaces.py -q
```

Expected: route-not-found or missing reader forwarding failure.

- [ ] **Step 3: Write failing real PostgreSQL repository tests**

Seed more than 100 active namespaces plus archived, private-only, fileless, and
namespace-only cases. Assert anonymous users see public candidates only;
members additionally see their namespace-only candidate; exact/prefix search
ranks correctly; and output never exceeds the requested limit.

- [ ] **Step 4: Run PostgreSQL tests and confirm RED**

Run the focused test with the repository's configured PostgreSQL test URL.
Expected: import failure for `read_searchable_skill_namespaces`.

- [ ] **Step 5: Implement the repository**

Add:

```python
async def read_searchable_skill_namespaces(
    engine: AsyncEngine,
    *,
    query: str | None,
    limit: int,
    current_user_id: str | None,
) -> list[dict[str, object]]:
    ...
```

Use `skill_search_document`, `skill`, `namespace`, a published-version
existence check, the same visibility membership condition as
`read_skill_search`, grouping by namespace, and deterministic ranking. Bind all
query text and limit values.

- [ ] **Step 6: Implement the route**

Add `GET /api/web/search/namespaces`, resolve optional session/mock/bearer
identity with `optional_current_user_id`, clamp the limit to 1..50, call the
reader, and wrap the list with `ok(...)`.

- [ ] **Step 7: Verify focused backend tests GREEN**

Run both focused files and relevant existing skill-search visibility tests.

### Task 2: API Contract And Query Hook

**Files:**
- Modify: `web/src/api/generated/schema.d.ts`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/client.ts`
- Create: `web/src/features/search/use-searchable-namespaces.ts`
- Create: `web/src/features/search/use-searchable-namespaces.test.ts`

- [ ] **Step 1: Add failing URL and query-key tests**

Assert omitted blank query, encoded non-blank query, capped limit forwarding,
and distinct cache keys for anonymous and authenticated identities.

- [ ] **Step 2: Confirm frontend RED**

Run the two focused client/hook test files. Expected: missing API method/hook.

- [ ] **Step 3: Regenerate the OpenAPI schema**

Start the current backend and run the repository's OpenAPI generation command.
Derive `SearchableNamespace` from the generated schema rather than manually
editing generated declarations.

- [ ] **Step 4: Implement API client and hook**

Add `searchApi.listNamespaces({ q, limit })` using `WEB_API_PREFIX`, and a
TanStack Query hook with `placeholderData` so prior candidates remain visible
during a debounced query transition.

- [ ] **Step 5: Verify focused tests GREEN**

Run the focused client and hook tests, typecheck, and generated-contract drift
check.

### Task 3: Reusable Namespace Filter

**Files:**
- Create: `web/src/features/search/namespace-search-filter.tsx`
- Create: `web/src/features/search/namespace-search-filter.test.tsx`
- Modify: `web/src/features/search/search-bar.tsx`
- Modify: `web/src/features/search/search-bar.test.ts`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [ ] **Step 1: Write failing picker tests**

Cover open-time default loading, 250 ms debounce, display-name/slug results,
single selection, all-namespaces clear, unknown selected slug, loading with
prior options, request error/retry, empty results, Escape, ArrowDown/ArrowUp,
and a maximum-height scroll container.

- [ ] **Step 2: Confirm picker RED**

Run the focused Vitest file. Expected: missing component.

- [ ] **Step 3: Implement the picker**

Use existing dropdown primitives. Keep selected slug controlled by the parent,
menu query local, query data in the hook, and translated status messages. Do
not alter the publish picker or shared Select.

- [ ] **Step 4: Extend SearchBar composition**

Add an optional `leadingControl: ReactNode` rendered inside the form. On mobile,
allow the form to wrap/stack without horizontal overflow; preserve current
behavior when the prop is absent.

- [ ] **Step 5: Verify component tests GREEN**

Run picker and SearchBar tests, then typecheck and lint the touched frontend.

### Task 4: Home, Landing, And Search Integration

**Files:**
- Modify: `web/src/pages/home.tsx`
- Modify: `web/src/pages/home.test.tsx`
- Modify: `web/src/pages/landing.tsx`
- Modify: `web/src/pages/landing.test.tsx`
- Modify: `web/src/pages/search.tsx`
- Modify: `web/src/pages/search.test.tsx`

- [ ] **Step 1: Write failing page tests**

Assert home and landing submit `{ q, namespace, sort: 'relevance', page: 0 }`,
an explicitly typed `@slug` overrides picker state, Search selection preserves
q/label/sort/starred and resets page, clearing keeps q, direct URL selection is
restored, and typed `@slug` synchronizes the picker.

- [ ] **Step 2: Confirm page tests RED**

Run the three focused page files. Expected: namespace controls or navigation
state missing.

- [ ] **Step 3: Integrate the pages**

Use one controlled slug per page. Home and landing parse submitted input; typed
namespace wins, otherwise use the picker slug. Search keeps visible input as
keyword text after picker changes while retaining support for direct `@slug`
input and existing debounced URL updates.

- [ ] **Step 4: Verify page tests GREEN**

Run all three page tests and existing search-query parser tests.

### Task 5: End-To-End And Regression Verification

**Files:**
- Create: `web/e2e/search-namespace-filter.spec.ts`
- Create: `docs/backend-python-maintenance/results/2026-08-12-search-namespace-filter.md`

- [ ] **Step 1: Add browser scenarios**

Verify anonymous and authenticated candidate visibility, more than 100 seeded
namespaces reached by server search, home/landing navigation, Search reload,
typed `@slug`, picker clear, keyboard use, and 390x844 viewport containment.

- [ ] **Step 2: Run focused real-service E2E**

Use containerized PostgreSQL and FastAPI plus the feature frontend. Verify root
and configured subpath routing where supported by the existing test harness.

- [ ] **Step 3: Run complete verification**

```powershell
cd server-python
uv run --no-cache pytest tests -q

cd ..\web
pnpm run test
pnpm run typecheck
pnpm run lint
pnpm run build

cd ..
git diff --check
```

- [ ] **Step 4: Perform code review**

Compare against `origin/dev` along documented standards and the design spec.
Review SQL visibility drift, information disclosure, query count/cache identity,
URL loops, stale picker state, mobile overflow, accessibility, and existing
starred-only behavior. Fix findings and rerun affected plus full verification.

- [ ] **Step 5: Record results and stop before integration**

Write exact commands/counts and residual risks to the result file. Leave the
branch uncommitted and unpushed for explicit user approval.
