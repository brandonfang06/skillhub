# Skill Subscription API Result

## Summary

Moved skill subscription read/create routes to Python:

- `GET /api/v1/skills/{skillId}/subscription`
- `GET /api/web/skills/{skillId}/subscription`
- `PUT /api/v1/skills/{skillId}/subscription`
- `PUT /api/web/skills/{skillId}/subscription`

`DELETE /subscription` was intentionally not moved. Live Java security currently blocks
`DELETE /api/v1/skills/{skillId}/subscription` for a normal local mock user with 403, while the web
alias still reaches Java through the fallback. This mirrors the star milestone boundary and keeps
unsubscribe for a later social/security cleanup milestone.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{skillId}/subscription` | java | python |
| GET | `/api/web/skills/{skillId}/subscription` | java | python |
| PUT | `/api/v1/skills/{skillId}/subscription` | java | python |
| PUT | `/api/web/skills/{skillId}/subscription` | java | python |
| DELETE | `/api/v1/skills/{skillId}/subscription` | java | java |
| DELETE | `/api/web/skills/{skillId}/subscription` | java | java |

## Implementation Notes

- Added `server-python/app/social/subscription.py` with explicit SQL helpers for skill existence,
  subscription lookup, idempotent insert, unsubscribe helper, and Java-compatible decrement logic.
- Extended `server-python/app/api/social.py` with `GET/PUT /subscription` routes.
- Anonymous subscription GET returns `false` without hitting the database, matching Java controller
  behavior observed through the live gate.
- Authenticated subscription GET validates skill existence and reads `skill_subscription`.
- Vite method-aware proxy now routes only subscription `GET` and `PUT` for v1/web to Python.
- Python direct `DELETE /subscription` is not exposed and returns 405.

## Java Parity Checklist

| Area | Outcome |
| --- | --- |
| API contract | Passed for `GET` and `PUT`: stable Java/Python/Vite envelopes match after ignoring volatile fields. |
| Authorization/session | Passed: anonymous `GET` returns false in Java, Python, and proxy. PUT requires `X-Mock-User-Id`. |
| Idempotency | Passed: repeated `PUT` does not duplicate `skill_subscription` and does not increment `subscription_count` again. |
| Counter parity | Passed: `skill.subscription_count` is 1 after subscribe in Java, Python, and proxy fixtures. |
| DELETE route parity | Deferred: Java v1 DELETE currently returns 403 for a normal user; Python direct route is not owned and returns 405; web DELETE remains Java-owned through proxy fallback. |
| Event parity | Deferred: Java emits subscribe/unsubscribe events for notification flows; Python has no social event bus yet. |
| Proxy boundary | Passed: Vite routes subscription `GET/PUT` to Python and leaves DELETE/rating/me-subscription outside Python ownership. |

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_subscription.py tests/test_skill_star.py tests/test_hybrid_makefile.py -q`
  - 16 passed, 1 Starlette/httpx deprecation warning.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - 25 passed.
- PowerShell syntax check for `scripts/dev-hybrid.ps1`
  - `syntax-ok`.
- Windows live gate:
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-subscription-smoke`
  - Python gate tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite skill subscription contract checks passed.
  - Playwright smoke passed: 6 passed.

Live gate route boundary evidence:

- anonymous subscription GET stable contract: Java/Python/proxy match with `data = false`.
- subscription PUT stable contract: Java/Python/proxy match.
- authenticated subscription GET stable contract: Java/Python/proxy match with `data = true`.
- DB state after subscribe: Java/Python/proxy all `true|1`.
- v1 unsubscribe boundary: Java 403, Python direct 405.
- web unsubscribe boundary: proxy web DELETE returned 200 through Java fallback and DB became `false|0`.
- Python direct rating PUT: 405.
- proxy `GET /api/v1/me/subscriptions`: 200 through Java fallback.

## Risks And Follow-Up

- `DELETE /subscription` needs a follow-up social/security cleanup milestone before Python route
  ownership moves. Do not add it to the Vite proxy until live Java behavior and intended product
  behavior are reconciled.
- Subscription events are deferred. Notification fan-out still depends on Java-owned workflows.
- Live gate cleanup printed warnings about elevated/foreign processes on port 8080 that could not
  be stopped by the script. The gate itself passed.

## Files

- `server-python/app/social/subscription.py`
- `server-python/app/api/social.py`
- `server-python/tests/test_skill_subscription.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-10-skill-subscription-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
