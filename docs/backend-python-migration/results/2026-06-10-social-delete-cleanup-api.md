# Social Delete Cleanup API Migration Result

**Date:** 2026-06-10

## Summary

Moved social delete routes to FastAPI:

- `DELETE /api/v1/skills/{skillId}/star`
- `DELETE /api/web/skills/{skillId}/star`
- `DELETE /api/v1/skills/{skillId}/subscription`
- `DELETE /api/web/skills/{skillId}/subscription`

This completes the Python-owned core social interaction state for star, subscription, rating, and
current-user social lists. `/api/v1|web/me/skills`, notification reads, and SSE remain Java-owned.

## Ownership Changes

| Method | Route | Before | After |
|--------|-------|--------|-------|
| DELETE | `/api/v1/skills/{skillId}/star` | java | python |
| DELETE | `/api/web/skills/{skillId}/star` | java | python |
| DELETE | `/api/v1/skills/{skillId}/subscription` | java | python |
| DELETE | `/api/web/skills/{skillId}/subscription` | java | python |

## Java Parity Outcome

Reference files inspected:

- `SkillStarController.java`
- `SkillSubscriptionController.java`
- `SkillStarService.java`
- `SkillSubscriptionService.java`
- `RouteSecurityPolicyRegistry.java`

Parity decisions:

- Python follows the Java controller/domain service behavior: authenticated DELETE returns update
  success with `data = null`.
- Unstar and unsubscribe are idempotent.
- Missing skill still returns `skill.not_found`.
- Star delete refreshes `skill.star_count`.
- Subscription delete decrements `skill.subscription_count` only when a row existed.
- Java v1 live security still blocks normal mock users on these numeric-id DELETE routes because the
  broad `DELETE /api/v1/skills/*/*` hard-delete policy matches first. This is recorded as a known
  Java route-policy mismatch, not a Python behavior target.

## Verification

Narrow checks:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_star.py tests/test_skill_subscription.py tests/test_skill_rating.py tests/test_my_social_lists.py tests/test_hybrid_makefile.py -q`
  - Passed: `24 passed, 1 warning`.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: `27 passed`.
- PowerShell syntax:
  - Passed: `syntax-ok`.

Windows live gates:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-star-smoke`
  - Passed.
  - Python gate tests: `11 passed, 1 warning`.
  - Vite proxy tests: `27 passed`.
  - Java/Python/Vite star create/read contracts matched.
  - Java v1 unstar normal-user status: `403`.
  - Python direct v1 unstar status: `200`, DB state became `false|0`.
  - Vite web unstar status: `200`, DB state became `false|0`.
  - Playwright smoke: `6 passed`.

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-subscription-smoke`
  - Passed.
  - Python gate tests: `11 passed, 1 warning`.
  - Vite proxy tests: `27 passed`.
  - Java/Python/Vite subscribe/read contracts matched.
  - Java v1 unsubscribe normal-user status: `403`.
  - Python direct v1 unsubscribe status: `200`, DB state became `false|0`.
  - Vite web unsubscribe status: `200`, DB state became `false|0`.
  - Playwright smoke: `6 passed`.

## Risks and Follow-Up

- Java v1 security mismatch is intentionally not fixed in `server/` because `server/` remains
  read-only. Python route ownership resolves the pre-launch frontend/API behavior.
- Java social events are still not implemented as an event bus in Python. The migrated Python
  workflows refresh counters synchronously; notification fan-out remains a later notification
  migration concern.
- PowerShell cleanup may warn when a port is owned by an elevated/foreign process; this did not
  affect the passing gates.

## Changed Files

- `server-python/app/api/social.py`
- `server-python/tests/test_skill_star.py`
- `server-python/tests/test_skill_subscription.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-10-social-delete-cleanup-api.md`
- `docs/backend-python-migration/results/2026-06-10-social-delete-cleanup-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
