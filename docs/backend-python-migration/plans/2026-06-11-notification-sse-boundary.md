# Notification SSE Boundary Migration Plan

## Summary

Move the notification SSE connection endpoints to FastAPI:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`

This closes the last explicit Java-owned non-OAuth route in `route-registry.md`. The milestone is a
connection-boundary migration: Python owns authentication rejection, `text/event-stream` response
format, initial `connected` event, and heartbeat comments. Full persisted-notification dispatch to
active SSE clients remains a later notification dispatcher/refactor task.

## Route Ownership

Python-owned after this milestone:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`

Unchanged ownership:

- Notification list/read/delete/preference APIs are already Python-owned.
- `/oauth2/**`, device flow, bearer-token authentication filters, scope enforcement, final session
  persistence, schema ownership, and Java decommission remain deferred.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NotificationController.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/sse/SseEmitterManager.java`
- `server/skillhub-notification/src/main/java/com/iflytek/skillhub/notification/service/NotificationDispatcher.java`
- `server/skillhub-app/src/test/java/com/iflytek/skillhub/exception/GlobalExceptionHandlerTest.java`

Expected behavior:

- Route requires an authenticated user.
- Successful connection returns an SSE stream with media type `text/event-stream`.
- Initial event is `event: connected` with `data: ok`.
- Heartbeats are SSE comments equivalent to Java `comment("ping")`.
- Java caps emitters and pushes persisted notification payloads through `NotificationDispatcher`.
  Python active-client fanout is deferred because Python notification writers currently write
  directly to persistence without a single dispatcher abstraction.

## Implementation Scope

Allowed edits:

- `server-python/app/api/notifications.py`
- `server-python/tests/test_notification_sse.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Generated OpenAPI TypeScript edits.
- OAuth/device-flow/bearer-token behavior changes.
- Notification storage schema changes.

## Test Plan

- Python tests:
  - unauthenticated SSE request returns HTTP 401 with `error.auth.required`;
  - authenticated SSE request returns `text/event-stream`;
  - SSE formatter emits Java-compatible `connected` event and heartbeat comment;
  - test override can emit a notification event payload in Java SSE format.
- Vite tests:
  - v1 and web SSE routes route to Python before `/api`;
  - `/oauth2/**` remains Java-owned.
- Windows live gate:
  - compare unauthenticated Java/Python/proxy SSE status;
  - verify authenticated Python SSE stream starts with `event: connected` and `data: ok`;
  - run Playwright smoke.

## Acceptance Criteria

- `cd server-python; uv run pytest tests/test_notification_sse.py tests/test_notifications.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell -ExecutionPolicy Bypass -File scripts/dev-hybrid.ps1 verify-notification-sse-boundary-smoke`
- `git diff --name-only -- server` prints nothing.
- Result doc records route ownership, verification, risks, and follow-up.
