# Skill Star API Result

## Summary

Moved authenticated skill star read/create routes to Python:

- `GET /api/v1/skills/{skillId}/star`
- `GET /api/web/skills/{skillId}/star`
- `PUT /api/v1/skills/{skillId}/star`
- `PUT /api/web/skills/{skillId}/star`

`DELETE /star` was intentionally not moved. Live Java security currently blocks
`DELETE /api/v1/skills/{skillId}/star` for a normal local mock user with 403, while the web alias
still reaches Java through the fallback. This milestone keeps both DELETE routes Java-owned until a
broader social/security cleanup milestone handles unstar.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{skillId}/star` | java | python |
| GET | `/api/web/skills/{skillId}/star` | java | python |
| PUT | `/api/v1/skills/{skillId}/star` | java | python |
| PUT | `/api/web/skills/{skillId}/star` | java | python |
| DELETE | `/api/v1/skills/{skillId}/star` | java | java |
| DELETE | `/api/web/skills/{skillId}/star` | java | java |

## Implementation Notes

- Added `server-python/app/social/star.py` with explicit SQL helpers for skill existence, star
  lookup, idempotent insert, idempotent unstar helper, and synchronous `skill.star_count` refresh.
- Added `server-python/app/api/social.py` and registered it before the broad skill router so
  numeric `/skills/{skillId}/star` routes are not swallowed by slug routes.
- Vite method-aware proxy now routes only star `GET` and `PUT` for v1/web to Python.
- Python direct `DELETE /star` is not exposed and returns 405.
- Rating/subscription/me-star routes remain outside Python ownership for this milestone.

## Java Parity Checklist

| Area | Outcome |
| --- | --- |
| API contract | Passed for `GET` and `PUT`: stable Java/Python/Vite envelopes match after ignoring volatile fields. |
| Authorization/session | Passed: anonymous `GET` is rejected with 401 in Java, Python, and proxy. Authenticated calls use `X-Mock-User-Id`. |
| Idempotency | Passed: repeated `PUT` does not duplicate `skill_star`. |
| Counter parity | Passed: `skill.star_count` is 1 after star in Java, Python, and proxy fixtures. |
| DELETE route parity | Deferred: Java v1 DELETE currently returns 403 for a normal user; Python direct route is not owned and returns 405; web DELETE remains Java-owned through proxy fallback. |
| Event parity | Deferred: Java emits star/unstar events; Python refreshes the counter synchronously and has no social event bus yet. |
| Proxy boundary | Passed: Vite routes star `GET/PUT` to Python and leaves DELETE/rating/subscription outside Python ownership. |

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_star.py tests/test_hybrid_makefile.py -q`
  - 11 passed, 1 Starlette/httpx deprecation warning.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - 24 passed.
- PowerShell syntax check for `scripts/dev-hybrid.ps1`
  - `syntax-ok`.
- Windows live gate:
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-star-smoke`
  - Python tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite skill star contract checks passed.
  - Playwright smoke passed: 6 passed.

Live gate route boundary evidence:

- anonymous star GET: Java 401, Python 401, proxy 401.
- star PUT stable contract: Java/Python/proxy match.
- authenticated star GET stable contract: Java/Python/proxy match.
- DB state after star: Java/Python/proxy all `true|1`.
- v1 unstar boundary: Java 403, Python direct 405.
- web unstar boundary: proxy web DELETE returned 200 through Java fallback and DB became `false|0`.
- Python direct rating/subscription PUT: both 405.
- Proxy rating/subscription PUT remained outside Python ownership; observed Java fallback statuses were 500 and 200 respectively.

## Risks And Follow-Up

- `DELETE /star` needs a follow-up social/security cleanup milestone before Python route ownership
  moves. Do not silently add it to the Vite proxy.
- Java v1 DELETE star appears to be caught by the broad
  `DELETE /api/v1/skills/*/*` route-security policy. That Java behavior was observed, not changed.
- Live gate cleanup printed warnings about an elevated/foreign process on port 8080 that could not
  be stopped by the script. The gate itself passed; future Windows cleanup may need a manual process
  stop or reboot if that process blocks the next run.

## Files

- `server-python/app/social/star.py`
- `server-python/app/api/social.py`
- `server-python/app/main.py`
- `server-python/tests/test_skill_star.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-10-skill-star-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
