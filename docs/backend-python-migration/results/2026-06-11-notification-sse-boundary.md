# Notification SSE Boundary Migration Result

## Summary

Moved the notification SSE connection endpoints to FastAPI:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`

This closes the last explicit Java-owned non-OAuth route in the route registry. The milestone
preserves the connection contract and keeps active persisted-notification fanout as a deferred
notification dispatcher/refactor task.

## Route Ownership

Before:

- `GET /api/v1/notifications/sse`: Java
- `GET /api/web/notifications/sse`: Java

After:

- `GET /api/v1/notifications/sse`: Python
- `GET /api/web/notifications/sse`: Python

Unchanged:

- Notification list/read/delete/preference APIs remain Python-owned.
- `/oauth2/**`, device flow, bearer-token authentication filters, scope enforcement, final session
  persistence, schema ownership, and Java decommission remain deferred.

## Implementation Notes

- SSE uses the existing Python hybrid auth bridge. Missing/unknown user returns HTTP 401 with
  `error.auth.required`.
- Authenticated connection returns `text/event-stream`.
- Initial event is Java-compatible:
  `event: connected` with `data: ok`.
- Heartbeat comments use the Java-compatible `: ping` SSE comment shape.
- Tests expose a stream factory hook so route behavior can be verified without hanging on an
  infinite stream.
- Active fanout from Python notification writers is deferred because current writers persist
  notifications directly instead of going through a unified dispatcher equivalent to Java
  `NotificationDispatcher`.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='C:\Users\USER\OneDrive\Documents\skillhub\.uv-cache'; uv run pytest tests/test_notification_sse.py tests/test_notifications.py tests/test_hybrid_makefile.py -q`
  - Result: `15 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `39 passed`
- Windows live gate:
  - `powershell -ExecutionPolicy Bypass -File scripts/dev-hybrid.ps1 verify-notification-sse-boundary-smoke`
  - Result: passed
  - Java/Python/proxy anonymous SSE statuses: `[401, 401, 401]`
  - Python authenticated first chunk:
    `event: connected\ndata: ok\n\n`
  - Proxy authenticated first chunk:
    `event: connected\ndata: ok\n\n`
  - Playwright smoke: `6 passed`
- Post-gate cleanup check:
  - `Get-NetTCPConnection -LocalPort 8080,8081,3000,8000 -State Listen -ErrorAction SilentlyContinue`
  - Result: no listener rows.

## Risks And Follow-Up

- Browser `EventSource` cannot send `X-Mock-User-Id`; production-grade cookie/session auth for SSE
  still depends on the final Python auth/session replacement.
- Persisted-notification fanout to connected Python SSE clients is deferred to a unified Python
  notification dispatcher/refactor milestone.
- `/api/**` fallback and `/oauth2/**` still require final proxy cleanup and auth strategy decisions.
