# My Social Lists API Migration Result

**Date:** 2026-06-10

## Summary

Moved current-user social list read routes to FastAPI:

- `GET /api/v1/me/stars`
- `GET /api/web/me/stars`
- `GET /api/v1/me/subscriptions`
- `GET /api/web/me/subscriptions`

`GET /api/v1|web/me/skills`, DELETE star/subscription routes, notifications, and SSE remain
Java-owned.

## Ownership Changes

| Method | Route | Before | After |
|--------|-------|--------|-------|
| GET | `/api/v1/me/stars` | java | python |
| GET | `/api/web/me/stars` | java | python |
| GET | `/api/v1/me/subscriptions` | java | python |
| GET | `/api/web/me/subscriptions` | java | python |
| GET | `/api/v1/me/skills` | java | java |
| GET | `/api/web/me/skills` | java | java |

## Implementation Notes

- Added `server-python/app/social/lists.py` with explicit `sqlalchemy.text` SQL.
- Added FastAPI routes in `server-python/app/api/social.py`.
- Preserved Java defaults: `page=0`, `size=12`.
- Preserved Java missing-skill behavior: joined skill rows determine `items`, while the social
  relationship table page total remains the response `total`.
- Reused the existing Java-compatible skill summary response mapper.
- Added method-aware Vite proxy entries for the four GET routes only.

## Verification

Narrow checks:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_my_social_lists.py tests/test_skill_star.py tests/test_skill_subscription.py tests/test_skill_rating.py tests/test_hybrid_makefile.py -q`
  - Passed: `24 passed, 1 warning`.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: `27 passed`.
- PowerShell syntax:
  - Passed: `syntax-ok`.

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-my-social-lists-smoke`
  - Passed.
  - Python gate tests: `19 passed, 1 warning`.
  - Vite proxy tests: `27 passed`.
  - Java/Python/Vite social list contracts matched.
  - Anonymous stars/subscriptions returned `401` across Java, Python, and proxy.
  - Vite proxy `/api/v1/me/skills` remained Java-owned and returned `200`.
  - Playwright smoke: `6 passed`.

Debug notes:

- First live gate failed because the fixture used `ON CONFLICT (namespace_id, slug)` on `skill`,
  but the current database schema has no unique constraint for that pair. The fixture now uses
  select-then-insert/update.
- Second live gate found only stable-comparison noise: Java serialized `ratingAvg` as `4.50`,
  while Python serialized `4.5`. The comparator now normalizes `ratingAvg` numerically.

## Risks and Follow-Up

- `canSubmitPromotion` parity is covered for global namespace fixtures where Java and Python both
  return `false`. Team namespace promotion eligibility should be covered when `/me/skills` or
  dashboard-owned skill lists migrate.
- DELETE star/subscription and notification fan-out remain deferred to a social/security cleanup
  milestone.
- PowerShell cleanup still may warn when it cannot stop a port owned by an elevated/foreign
  process; this did not affect the passing gate.

## Changed Files

- `server-python/app/social/lists.py`
- `server-python/app/api/social.py`
- `server-python/tests/test_my_social_lists.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-10-my-social-lists-api.md`
- `docs/backend-python-migration/results/2026-06-10-my-social-lists-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
