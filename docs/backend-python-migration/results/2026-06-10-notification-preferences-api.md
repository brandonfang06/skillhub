# Notification Preferences API Migration Result

**Date:** 2026-06-10

## Summary

Moved authenticated notification preference read/update routes to FastAPI and Vite method-aware
proxy. Notification SSE remains Java-owned.

## Routes Changed

Python-owned:

- `GET /api/v1/notification-preferences`
- `GET /api/web/notification-preferences`
- `PUT /api/v1/notification-preferences`
- `PUT /api/web/notification-preferences`

Still Java-owned:

- `GET /api/v1/notifications/sse`
- `GET /api/web/notifications/sse`

## Behavior Notes

- GET returns all Java `NotificationCategory` values in enum order:
  `PUBLISH`, `REVIEW`, `PROMOTION`, `REPORT`.
- Only `IN_APP` channel is currently valid because Java `NotificationChannel` currently defines
  only `IN_APP`.
- Missing stored preference rows default to `enabled = true`.
- PUT rejects missing `preferences`, invalid category/channel strings, and duplicate
  category/channel pairs.
- PUT upserts rows in `notification_preference` and returns the full preference list after update.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_notification_preferences.py tests/test_notifications.py tests/test_hybrid_makefile.py -q`
  - `16 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `28 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-notification-preferences-smoke`
  - Python/hybrid tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite GET preference stable JSON matched.
  - Java/Python/Vite PUT preference stable JSON matched.
  - Invalid category, invalid channel, and duplicate payloads returned `400` across Java/Python/Vite.
  - Anonymous proxy access returned `401`.
  - Notification SSE stayed Java-owned.
  - Playwright smoke passed: `6 passed`.
- `git diff --name-only -- server`
  - no paths.

## Risks / Follow-Up

- SSE is still Java-owned and should remain a separate streaming milestone if migrated.
- If Java adds future notification channels, Python channel validation must be updated with the
  same enum behavior and service-level unsupported rules.
