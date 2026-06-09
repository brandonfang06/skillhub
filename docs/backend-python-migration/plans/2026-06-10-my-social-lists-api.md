# My Social Lists API Migration Plan

**Date:** 2026-06-10

**Goal:** Move current-user starred and subscribed skill list reads from Java to FastAPI.

**Milestone group:** Group F - Social, Ratings, Subscriptions, Notifications.

## Route Ownership

Move to Python:

- `GET /api/v1/me/stars`
- `GET /api/web/me/stars`
- `GET /api/v1/me/subscriptions`
- `GET /api/web/me/subscriptions`

Remain Java-owned:

- `GET /api/v1/me/skills`
- `GET /api/web/me/skills`
- `DELETE /api/v1/skills/{skillId}/star`
- `DELETE /api/web/skills/{skillId}/star`
- `DELETE /api/v1/skills/{skillId}/subscription`
- `DELETE /api/web/skills/{skillId}/subscription`
- Notification reads and SSE routes.

## Java Contract

Reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/MeController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/MySkillAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/JpaMySkillQueryRepository.java`

Contract:

- Routes require an authenticated `PlatformPrincipal`; anonymous requests return `error.auth.required`.
- Query params use Java defaults: `page=0`, `size=12`.
- List order follows the `skill_star` or `skill_subscription` repository page order.
- Missing skill rows are filtered out of the returned `items`, while `total` remains the social table page total.
- Response envelope is `response.success.read`.
- `SkillSummaryResponse` includes lifecycle projection fields from the viewer/owner summary projection.

## Python Implementation Boundaries

Allowed edits:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden edits:

- Any file under `server/`.

## Data Access Strategy

Use explicit `sqlalchemy.text` SQL for this migration phase, matching the current documented Python
data-access strategy. Do not introduce SQLAlchemy ORM models in this milestone.

## Testing Plan

- Add failing Python tests for:
  - unauthenticated route rejection,
  - stars and subscriptions page defaults,
  - Java-compatible missing-skill filtering with unchanged `total`,
  - summary response shape including lifecycle projection fields.
- Add Vite proxy tests proving only the four new GET routes point to Python.
- Add Windows live gate:
  - create Java/Python/proxy fixtures,
  - seed star and subscription rows,
  - compare Java/Python/proxy stable response JSON,
  - verify anonymous rejection,
  - verify `/api/v1/me/skills` remains Java-owned,
  - run Playwright smoke after the hybrid stack is up.

## Checklist

- [x] Add failing Python tests.
- [x] Implement Python social list query and FastAPI routes.
- [x] Add failing Vite proxy tests.
- [x] Route the four GET paths to Python.
- [x] Add Windows live gate.
- [x] Update route registry and sequence plan.
- [x] Run narrow tests.
- [x] Run Windows live gate.
- [x] Confirm `git diff --name-only -- server` is empty.
- [x] Write result document.
- [ ] Commit and push.
