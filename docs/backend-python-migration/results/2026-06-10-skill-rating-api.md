# Skill Rating API Result

## Summary

Moved skill rating read/create/update routes to Python:

- `GET /api/v1/skills/{skillId}/rating`
- `GET /api/web/skills/{skillId}/rating`
- `PUT /api/v1/skills/{skillId}/rating`
- `PUT /api/web/skills/{skillId}/rating`

The route accepts Java-compatible `{ "score": number }`, validates scores 1..5, creates or updates
the current user's `skill_rating` row, and refreshes `skill.rating_avg` / `skill.rating_count`
synchronously for deterministic Python behavior.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{skillId}/rating` | java | python |
| GET | `/api/web/skills/{skillId}/rating` | java | python |
| PUT | `/api/v1/skills/{skillId}/rating` | java | python |
| PUT | `/api/web/skills/{skillId}/rating` | java | python |

## Implementation Notes

- Added `server-python/app/social/rating.py` with explicit SQL helpers for skill existence, score
  validation, current user rating lookup, create/update, and aggregate refresh.
- Extended `server-python/app/api/social.py` with `GET/PUT /rating` routes and a small Pydantic
  request model.
- Vite method-aware proxy now routes only rating `GET` and `PUT` for v1/web to Python.
- `GET /api/v1/me/stars` and `GET /api/v1/me/subscriptions` remain Java-owned through the fallback.

## Java Parity Checklist

| Area | Outcome |
| --- | --- |
| API contract | Passed: Java/Python/Vite stable envelopes match for initial read, create, update, and final read. |
| Authorization/session | Passed: anonymous rating GET is rejected with 401 in Java, Python, and proxy. |
| Validation | Passed: score `0` is rejected with 400 in Java, Python, and proxy. |
| Skill existence validation | Covered by Python unit tests: missing skill is checked before score validation. |
| Aggregate parity | Passed: after create score 4 and update score 2, all DB states are `true|2|2.00|1`. |
| Event parity | Deferred: Java emits rating events and updates aggregates asynchronously; Python refreshes aggregates synchronously and has no social event bus yet. |
| Proxy boundary | Passed: Vite routes rating `GET/PUT` to Python and keeps me-social lists Java-owned. |

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_rating.py tests/test_skill_subscription.py tests/test_skill_star.py tests/test_hybrid_makefile.py -q`
  - 21 passed, 1 Starlette/httpx deprecation warning.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - 26 passed.
- PowerShell syntax check for `scripts/dev-hybrid.ps1`
  - `syntax-ok`.
- Windows live gate:
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-rating-smoke`
  - Python gate tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite rating contract checks passed.
  - Playwright smoke passed: 6 passed.

Live gate evidence:

- anonymous rating GET: Java 401, Python 401, proxy 401.
- initial authenticated read: Java/Python/proxy match with `score = 0`, `rated = false`.
- score 4 PUT stable contract: Java/Python/proxy match.
- score 2 update PUT stable contract: Java/Python/proxy match.
- final authenticated read: Java/Python/proxy match with `score = 2`, `rated = true`.
- DB state after update: Java/Python/proxy all `true|2|2.00|1`.
- invalid score 0: Java 400, Python 400, proxy 400.
- proxy `GET /api/v1/me/stars`: 200 through Java fallback.
- proxy `GET /api/v1/me/subscriptions`: 200 through Java fallback.

## Risks And Follow-Up

- Python refreshes rating aggregates synchronously while Java uses an async transactional listener.
  This is intentionally deterministic for pre-launch migration and live comparison.
- Social event fan-out remains deferred. Notification reads/SSE are still Java-owned.
- Live gate cleanup printed warnings about elevated/foreign processes on port 8080 that could not
  be stopped by the script. The gate itself passed.

## Files

- `server-python/app/social/rating.py`
- `server-python/app/api/social.py`
- `server-python/tests/test_skill_rating.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-10-skill-rating-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
