# Notification Preferences API Migration Plan

**Date:** 2026-06-10

**Goal:** Move notification preference read/update routes from Java to FastAPI while keeping
notification SSE Java-owned.

**Milestone group:** Group F - Social, Ratings, Subscriptions, Notifications.

## Route Ownership

Move to Python:

- `GET /api/v1/notification-preferences`
- `GET /api/web/notification-preferences`
- `PUT /api/v1/notification-preferences`
- `PUT /api/web/notification-preferences`

Remain Java-owned:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`

## Java Contract

Reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NotificationPreferenceController.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/service/NotificationPreferenceService.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/domain/NotificationPreference.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/domain/NotificationPreferenceRepository.java`
- `server/skillhub-app/src/main/resources/db/migration/V37__notification_system.sql`

Contract:

- Routes require authenticated local user context.
- GET returns all `NotificationCategory` values in Java enum order:
  `PUBLISH`, `REVIEW`, `PROMOTION`, `REPORT`.
- Only `IN_APP` channel is supported.
- Missing stored preferences default to `enabled = true`.
- PUT request body must contain non-null `preferences`.
- PUT rejects invalid category with `error.notification.preference.category.invalid`.
- PUT rejects invalid channel with `error.notification.preference.channel.invalid`.
- PUT rejects duplicate category/channel pairs with `error.notification.preference.duplicate`.
- Java currently defines only `IN_APP`; any other channel string is rejected as
  `error.notification.preference.channel.invalid` before the service-level unsupported guard can
  run.
- PUT upserts preference rows and returns the full GET shape after update.

## Python Implementation Boundaries

Allowed edits:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden edits:

- Any file under `server/`.
- Generated frontend API types.

## Data Access Strategy

Use explicit `sqlalchemy.text` SQL against the Java-owned `notification_preference` table. Do not
introduce ORM models or schema migrations.

## Testing Plan

- Add failing Python tests for:
  - GET default full preference list,
  - saved preference overlay,
  - PUT duplicate validation,
  - invalid category/channel validation,
  - unsupported channel guard,
  - upsert behavior and full response,
  - route envelopes and auth boundaries.
- Add failing Vite proxy tests for preference GET/PUT while notification SSE remains Java-owned.
- Add Windows live gate:
  - seed users and preference rows,
  - compare Java/Python/Vite GET stable JSON,
  - verify PUT update shape and DB effects,
  - verify invalid category and duplicate payload rejection,
  - verify notification SSE remains Java-owned,
  - run Playwright smoke.

## Checklist

- [x] Add failing Python notification preference tests.
- [x] Implement Python notification preference service/routes.
- [x] Add failing Vite proxy tests.
- [x] Route notification preference GET/PUT to Python.
- [x] Add Windows live gate.
- [x] Update route registry and sequence plan.
- [x] Run narrow tests.
- [x] Run Windows live gate.
- [x] Confirm `git diff --name-only -- server` is empty.
- [x] Write result document.
- [x] Commit and push.
