# Notification Read API Migration Plan

**Date:** 2026-06-10

**Goal:** Move standard user notification read and read-state routes from Java to FastAPI, while
leaving SSE and preferences for later.

**Milestone group:** Group F - Social, Ratings, Subscriptions, Notifications.

## Route Ownership

Move to Python:

- `GET /api/v1/notifications`
- `GET /api/web/notifications`
- `GET /api/v1/notifications/unread-count`
- `GET /api/web/notifications/unread-count`
- `PUT /api/v1/notifications/{id}/read`
- `PUT /api/web/notifications/{id}/read`
- `PUT /api/v1/notifications/read-all`
- `PUT /api/web/notifications/read-all`
- `DELETE /api/v1/notifications/{id}`
- `DELETE /api/web/notifications/{id}`

Remain Java-owned:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`
- `GET/PUT /api/v1|web/notification-preferences`
- `GET/POST /api/v1|web/governance/notifications...`

## Java Contract

Reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NotificationController.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/service/NotificationService.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/domain/Notification.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/domain/NotificationRepository.java`
- `server/skillhub-app/src/main/resources/db/migration/V37__notification_system.sql`

Contract:

- Routes require the authenticated local user context.
- List defaults: `page=0`, `size=20`, valid `size` range 1..100.
- Optional `category` must be one of `PUBLISH`, `REVIEW`, `PROMOTION`, `REPORT`; invalid category
  returns `error.notification.category.invalid`.
- List order is `created_at DESC`.
- Unread count returns `{ "count": <long> }`.
- Mark single read:
  - Missing id returns `error.notification.notFound`.
  - Foreign id returns `error.notification.noPermission`.
  - Success returns update success with `data = null`.
- Mark all read returns update success with `{ "updated": <count> }`.
- Delete only deletes notifications that belong to the user and are already `READ`; otherwise returns
  `error.notification.readNotFound`.
- Notification target fields follow Java `resolveTarget` logic.

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

Use explicit `sqlalchemy.text` SQL against the Java-owned `notification` table. Do not introduce
ORM models or schema migrations.

## Testing Plan

- Add failing Python tests for:
  - response mapping and target resolution,
  - category validation,
  - list/default pagination,
  - unread count,
  - mark-read missing/foreign/success,
  - mark-all-read count,
  - delete-read read-only rule,
  - route envelopes and auth boundaries.
- Add failing Vite proxy tests for moved routes while SSE/preferences/governance notifications stay
  Java-owned.
- Add Windows live gate:
  - seed representative notifications,
  - compare Java/Python/Vite list and unread-count stable JSON,
  - verify mark-read, mark-all-read, delete-read DB effects,
  - verify invalid category and forbidden/missing delete behavior,
  - verify SSE and preferences remain Java-owned,
  - run Playwright smoke.

## Known Frontend/API Drift

`web/src/api/client.ts` currently types `markAllRead()` as returning `{ count: number }`, while Java
returns `{ updated: number }`. This milestone preserves Java contract and documents the drift; it
does not edit frontend API client code unless a later frontend cleanup milestone explicitly changes
that surface.

## Checklist

- [x] Add failing Python notification tests.
- [x] Implement Python notification query/workflow/routes.
- [x] Add failing Vite proxy tests.
- [x] Route notification read/read-state paths to Python.
- [x] Add Windows live gate.
- [x] Update route registry and sequence plan.
- [x] Run narrow tests.
- [x] Run Windows live gate.
- [x] Confirm `git diff --name-only -- server` is empty.
- [x] Write result document.
- [x] Commit and push.
