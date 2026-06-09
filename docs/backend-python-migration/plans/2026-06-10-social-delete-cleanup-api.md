# Social Delete Cleanup API Migration Plan

**Date:** 2026-06-10

**Goal:** Move skill unstar and unsubscribe routes to FastAPI so the social interaction slice is
coherently Python-owned.

**Milestone group:** Group F - Social, Ratings, Subscriptions, Notifications.

## Route Ownership

Move to Python:

- `DELETE /api/v1/skills/{skillId}/star`
- `DELETE /api/web/skills/{skillId}/star`
- `DELETE /api/v1/skills/{skillId}/subscription`
- `DELETE /api/web/skills/{skillId}/subscription`

Already Python-owned and kept in this group:

- `GET/PUT /api/v1|web/skills/{skillId}/star`
- `GET/PUT /api/v1|web/skills/{skillId}/subscription`
- `GET/PUT /api/v1|web/skills/{skillId}/rating`
- `GET /api/v1|web/me/stars`
- `GET /api/v1|web/me/subscriptions`

Remain Java-owned:

- `GET /api/v1|web/me/skills`
- Notification reads and SSE routes.
- Broader hard-delete skill routes such as `DELETE /api/v1/skills/{namespace}/{slug}`.

## Java Contract

Reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillStarController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillSubscriptionController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillStarService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillSubscriptionService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`

Contract:

- DELETE routes require an authenticated user.
- Missing skill returns `skill.not_found`.
- Unstar/unsubscribe are idempotent: deleting a missing relationship still returns update success.
- Star delete refreshes `skill.star_count`.
- Subscription delete decrements `skill.subscription_count` only when a row existed.
- Response envelope is update success with `data = null`.

Important live-Java note:

- Current Java v1 security has a broad `DELETE /api/v1/skills/*/*` SUPER_ADMIN policy. In live
  comparison this catches `DELETE /api/v1/skills/{skillId}/star` and blocks a normal mock user
  before the controller can run.
- This milestone intentionally follows the Java controller/domain service contract rather than
  preserving that pre-launch route-policy mismatch. The live gate will compare Python v1/web and
  Java web behavior for normal-user success, and record Java v1 as the known security mismatch.

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

Use existing explicit SQL helpers in `app.social.star` and `app.social.subscription`. Do not add
ORM models or schema migrations.

## Testing Plan

- Update Python route tests so DELETE star/subscription returns update success, requires auth, and
  no longer returns 405.
- Keep service tests for idempotent unstar/unsubscribe and counter updates.
- Update Vite proxy tests so DELETE on the social routes goes to Python while broader skill delete
  remains Java-owned.
- Add/extend Windows live gate to verify:
  - Python direct DELETE success and idempotency.
  - Vite proxy DELETE success and state changes.
  - Java web DELETE success as the comparison oracle for the intended controller/service behavior.
  - Java v1 DELETE normal-user status is recorded as the known route-policy mismatch.
  - `/api/v1/me/skills` and broader hard-delete routes remain Java-owned.

## Checklist

- [x] Add failing Python route tests for DELETE star/subscription.
- [x] Add failing Vite proxy tests for DELETE route ownership.
- [x] Implement FastAPI DELETE routes.
- [x] Update Vite method-aware proxy ownership.
- [x] Add/extend Windows live gate.
- [x] Update route registry and sequence plan.
- [x] Run narrow tests.
- [x] Run Windows live gate.
- [x] Confirm `git diff --name-only -- server` is empty.
- [x] Write result document.
- [ ] Commit and push.
