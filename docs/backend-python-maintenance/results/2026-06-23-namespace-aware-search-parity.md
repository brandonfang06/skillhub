# Namespace-Aware Search Parity Result

Date: 2026-06-23

## Summary

Python search now matches upstream `v0.2.12` visibility semantics for portal,
ClawHub-compatible, and CLI search routes.

- Anonymous search returns `PUBLIC` skills only.
- Authenticated search returns `PUBLIC` plus `NAMESPACE_ONLY` skills when the
  user is a member of the skill namespace.
- `PRIVATE` skills remain excluded from portal/global search.
- CLI search now accepts `X-Mock-User-Id` consistently with CLI resolve and
  download routes, so local mock-auth CLI testing is not forced into anonymous
  search.
- Frontend search query keys are partitioned by authenticated user id or
  `anonymous`, preventing user-specific namespace search results from being
  reused across sessions.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/app/skills/read_repository.py`
- `server-python/tests/test_skill_search.py`
- `server-python/tests/test_clawhub_search.py`
- `server-python/tests/test_clawhub_skills_list.py`
- `server-python/tests/test_cli_skills.py`
- `server-python/tests/test_mock_auth_cli_flow.py`
- `server-python/tests/test_mock_auth_user_discovery_flow.py`
- `server-python/tests/test_skill_search_repository.py`
- `web/src/shared/hooks/query-keys.ts`
- `web/src/shared/hooks/use-skill-queries.ts`
- `web/src/shared/hooks/use-skill-queries.test.ts`

## Verification

```powershell
cd server-python
uv run pytest tests/test_skill_search.py tests/test_clawhub_search.py tests/test_skill_search_repository.py -q
uv run pytest tests/test_clawhub_skills_list.py tests/test_mock_auth_cli_flow.py tests/test_mock_auth_user_discovery_flow.py tests/test_cli_skills.py tests/test_skill_search.py tests/test_clawhub_search.py tests/test_skill_search_repository.py -q
uv run pytest tests -q

cd ..\web
corepack pnpm exec vitest run src/shared/hooks/use-skill-queries.test.ts src/shared/hooks/skill-query-helpers.test.ts src/shared/lib/skill-download-cache.test.ts src/features/notification/notification-session.test.ts
corepack pnpm run typecheck
corepack pnpm run lint

cd ..
git diff --check
```

Results:

- Initial backend red tests failed for missing `current_user_id` route
  forwarding and missing repository `current_user_id` search scope.
- Initial frontend red test failed because `getSkillSearchQueryKey` did not
  exist.
- Targeted backend tests after implementation: `33 passed, 1 warning`.
- Targeted frontend tests after implementation: `4 passed`, `10 passed`.
- Full backend suite: `833 passed, 1 warning`.
- Frontend typecheck: passed.
- Frontend lint: passed.
- `git diff --check`: passed with Windows line-ending warnings only.
