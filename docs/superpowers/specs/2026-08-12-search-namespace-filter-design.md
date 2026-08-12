# Search Namespace Filter Design

Date: 2026-08-12

## Goal

Add a single-select namespace filter to the authenticated home search bar, the
public landing search bar, and the Search page without rendering every
namespace when the registry contains more than 100 namespaces.

## User Experience

The search surfaces show a compact namespace trigger beside the keyword input.
The trigger opens a searchable menu with an `All namespaces` choice and at most
20 namespace candidates. Typing searches namespace display names and slugs on
the server. The selected option is shown as `Display Name (@slug)`.

On the home and landing pages, submitting a keyword and optional namespace
navigates to `/search` with separate `q` and `namespace` parameters. On the
Search page, selecting or clearing a namespace updates the same URL state,
resets pagination to page zero, and keeps the keyword, label, sort, and starred
state.

The existing leading syntax remains supported:

```text
@team-ai code review
```

Typing that syntax updates the namespace picker to `team-ai`. Choosing a
namespace in the picker displays the keyword without injecting `@team-ai` into
the visible text input. Clearing the picker preserves the keyword. A selected
slug that is not present in the current 20 candidates remains visible as
`@slug` and can be cleared.

## Candidate API

Add `GET /api/web/search/namespaces` with these query parameters:

- `q`: optional namespace display-name or slug substring, trimmed and matched
  case-insensitively.
- `limit`: optional result limit, default 20, constrained to 1 through 50.

The response is the standard envelope containing a list of:

```json
{
  "slug": "team-ai",
  "displayName": "AI Platform",
  "visibleSkillCount": 17
}
```

Candidates include only non-archived namespaces with at least one searchable skill
for the current request identity. The repository applies the same effective
rules as portal search:

- anonymous: `PUBLIC` skills only;
- authenticated: `PUBLIC` plus `NAMESPACE_ONLY` skills in namespaces where the
  user is a member;
- exclude private, hidden, archived, unpublished, or fileless skills while
  retaining read-only `FROZEN` namespaces that portal search still exposes.

An empty candidate query orders by visible skill count descending, then display
name and slug. A non-empty query prioritizes exact slug, exact display name,
prefix matches, then visible skill count and stable alphabetical ordering.
This keeps useful defaults while allowing all 100+ namespaces to be reached by
typing.

## Frontend Architecture

Create a Search feature component and hook:

- `useSearchableNamespaces(query, enabled)` uses TanStack Query and partitions
  cache by request identity through the same authenticated fetch boundary.
- `NamespaceSearchFilter` owns open/query UI state and emits a slug or an empty
  string. It uses the existing Radix dropdown primitives and keeps a bounded,
  scrollable menu.
- Home, landing, and Search pages own the selected slug because navigation and
  URL semantics belong to the page.

No shared Select behavior changes. No namespace administration or membership
API is reused because those endpoints do not represent all namespaces whose
skills are searchable by the current identity.

## Loading And Failure Behavior

- Opening the menu immediately shows cached/default candidates when available.
- While a new namespace query is loading, keep prior candidates visible and
  show a small progress indicator.
- A failed candidate request shows a translated retryable status inside the
  menu but does not break keyword search or an already selected namespace.
- Empty results show a translated `No matching namespaces` message.
- Namespace typing is debounced to avoid one request per keystroke.

## Compatibility And Side Effects

- Existing `@namespace` parsing and direct `namespace` URLs remain valid.
- The skill-search endpoint and response shape remain unchanged.
- Namespace selection is single-select and exact by slug.
- Search visibility is not broadened. The candidate endpoint must never expose
  a namespace solely because it exists or because the user administers it.
- The Search page starred-only client filter continues applying the selected
  namespace exactly as it does today.
- Root and `/skillhub` deployments use the existing base-path-aware API and
  router helpers.

## Verification

- Repository tests prove anonymous and authenticated SQL visibility rules and
  verify archived/private/fileless exclusions, ranking, query, and limit. The
  query is also executed against the real local PostgreSQL service.
- Route tests verify the response envelope, optional auth forwarding, and input
  boundaries.
- Frontend tests cover server-search debounce, selection, clearing, loading,
  errors, empty results, unknown selected slugs, and keyboard behavior.
- Page tests cover home/landing navigation and Search URL synchronization with
  both picker selection and `@slug` input.
- Authenticated and anonymous browser tests exercise more than 100 candidate
  namespaces on desktop and a 390-pixel viewport, including root/subpath-safe
  navigation and reload restoration.

## Out Of Scope

- Multi-select namespaces.
- Namespace creation or membership management.
- Returning all namespace candidates in one response.
- Changing skill relevance or visibility rules.
