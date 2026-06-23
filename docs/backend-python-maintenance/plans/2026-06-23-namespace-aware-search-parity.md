# Namespace-Aware Search Parity Plan

Date: 2026-06-23

## Goal

Make the Python backend match upstream `v0.2.12` search visibility semantics:
anonymous search returns `PUBLIC` skills only, while authenticated portal and
compat search returns `PUBLIC` plus `NAMESPACE_ONLY` skills in namespaces where
the user is a member.

## Upstream Evidence

Checked against fetched `upstream/main` and tag `v0.2.12`.

- `SkillSearchController` passes `userId` and `userNsRoles` into
  `SkillSearchAppService`.
- `SkillSearchAppService` builds `SearchVisibilityScope` from
  `userNsRoles.keySet()`.
- `PostgresFullTextQueryService` filters with:
  `d.visibility = 'PUBLIC' OR (d.visibility = 'NAMESPACE_ONLY' AND d.namespace_id IN :memberNamespaceIds)`.
- Upstream anonymous search tests assert public-only search.
- Upstream authenticated search tests assert member namespace ids are included.

## Current Python Gap

- `server-python/app/api/skills.py` does not resolve optional current user
  context for `/api/web/skills`, `/api/v1/search`, or `/api/v1/skills` listing.
- `server-python/app/skills/read_repository.py::read_skill_search` filters
  `d.visibility = 'PUBLIC'` unconditionally.
- Frontend search query cache keys are currently user-agnostic even though the
  response will become user-dependent.

## Milestone Scope

1. Add failing backend tests for route current-user forwarding and repository
   namespace-aware search SQL.
2. Add failing frontend query-key test for user-scoped search cache keys.
3. Implement optional current-user propagation in search/list routes.
4. Implement repository visibility filtering:
   - anonymous: `PUBLIC` only.
   - authenticated: `PUBLIC` or `NAMESPACE_ONLY` with a matching
     `namespace_member` row.
   - do not include `PRIVATE` in portal/global search.
   - keep installable-only filters before count and page queries.
5. Partition frontend search query keys by authenticated user id, with
   `anonymous` as the guest scope.
6. Verify targeted tests, full backend tests, frontend typecheck/test, and
   `git diff --check`.

## Verification

```powershell
cd server-python
uv run pytest tests/test_skill_search.py tests/test_clawhub_search.py tests/test_cli_skills.py tests/test_skill_search_repository.py -q
uv run pytest tests -q

cd ..\web
corepack pnpm exec vitest run src/shared/hooks/use-skill-queries.test.ts src/shared/hooks/skill-query-helpers.test.ts src/shared/lib/skill-download-cache.test.ts src/features/notification/notification-session.test.ts
corepack pnpm run typecheck

cd ..
git diff --check
```

## Success Criteria

- A namespace member can find approved `NAMESPACE_ONLY` skills through homepage
  search.
- Anonymous users still cannot find `NAMESPACE_ONLY` skills.
- Search never exposes `PRIVATE` skills.
- Frontend search cache entries cannot be reused across different authenticated
  users.
