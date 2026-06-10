# Notification Read API Migration Result

**Date:** 2026-06-10

## Summary

Moved authenticated notification read/read-state routes to FastAPI and Vite method-aware proxy.
SSE streams and notification preferences remain Java-owned.

## Routes Changed

Python-owned:

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

Still Java-owned:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`
- `GET/PUT /api/v1/notification-preferences`
- `GET/PUT /api/web/notification-preferences`

## Behavior Notes

- Notification list preserves Java `PageResponse` shape: `items`, `total`, `page`, `size`.
- Category validation is Java-compatible and case-sensitive.
- Target resolution mirrors Java for review, promotion, report, skill, and fallback targets.
- Mark-one-read success returns Java-compatible update envelope with `data = null`.
- Mark-all-read returns Java-compatible `{ "updated": <count> }`.
- Delete only removes current-user `READ` notifications; unread/missing/foreign deletes return
  `error.notification.readNotFound`.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_notifications.py tests/test_hybrid_makefile.py -q`
  - `12 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `28 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-notification-read-smoke`
  - Python/hybrid tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite stable notification list comparison passed.
  - Category invalid rejection matched `400` across Java/Python/Vite.
  - Mark-read, mark-all-read, and delete-read DB effects passed.
  - SSE and preferences boundary checks stayed Java-owned.
  - Playwright smoke passed: `6 passed`.
- `git diff --name-only -- server`
  - no paths.

## Risks / Follow-Up

- Frontend API client still types `markAllRead()` as `{ count }`, while Java and Python return
  `{ updated }`; keep this as a later frontend contract cleanup.
- Notification preferences are not migrated yet.
- SSE remains Java-owned and should be planned separately because it is a streaming endpoint.
