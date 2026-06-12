# Notification SSE Fanout Result

Date: 2026-06-12

## Summary

Milestone 117 completed active notification SSE delivery for the single Python backend runtime path.

- Added `NotificationFanoutManager` for connected SSE clients.
- Added Java-compatible SSE formatting for connected, heartbeat, and notification events.
- Added `build_notification_sse_payload(...)` with the same field set used by Java
  `NotificationDispatcher`: `id`, `category`, `eventType`, `title`, `bodyJson`, `entityType`,
  `entityId`, and `createdAt`.
- Wired `GET /api/v1/notifications/sse` and `GET /api/web/notifications/sse` to the app-level
  fanout manager.
- Wired skill report submission to publish created `notification` rows after the database
  transaction commits.

## Scope Note

This milestone implements active fanout inside the Python backend process. The pre-launch target is a
single Python backend runtime, so this closes the current Java dependency for SSE delivery. If the
deployment later runs multiple Python backend replicas, the same publisher payload should be bridged
through Redis pub/sub or Redis streams so notifications created by one replica can reach SSE clients
connected to another replica.

## TDD Evidence

Red run:

- `uv run pytest tests/test_notification_sse_fanout.py tests/test_skill_report_submit.py -q`
  - Expected failure: `app.notifications.fanout` did not exist.

Green runs:

- `uv run pytest tests/test_notification_sse_fanout.py tests/test_skill_report_submit.py tests/test_notification_sse.py -q`
  - Result: 10 passed, 1 warning.
- `uv run pytest tests/test_notification_sse_fanout.py tests/test_notification_sse.py tests/test_notifications.py tests/test_notification_preferences.py tests/test_skill_report_submit.py tests/test_hybrid_makefile.py -q`
  - Result: 26 passed, 1 warning.
- `python -m compileall` on the touched notification, skill report, and app bootstrap modules.

## Live Verification

Hybrid stack was started with:

- `.\scripts\dev-hybrid.ps1 -Action up`

Then a live Python/httpx check seeded a reportable skill, opened a Python SSE stream for a
`SKILL_ADMIN`, submitted a report through the Python report endpoint, and read the notification from
the same SSE stream.

Observed live evidence:

- SSE connected chunk: `event: connected`, `data: ok`.
- Report submit response: `{"reportId":65,"status":"PENDING"}`.
- SSE notification payload:
  - `category`: `REPORT`
  - `eventType`: `REPORT_SUBMITTED`
  - `title`: `Skill reported: Codex SSE Skill`
  - `entityType`: `REPORT`
  - `entityId`: `65`
  - `createdAt`: `2026-06-12T05:55:31.234813Z`

Hybrid stack was stopped afterward with:

- `.\scripts\dev-hybrid.ps1 -Action down`

## Files Changed

- `server-python/app/notifications/fanout.py`
- `server-python/app/notifications/publisher.py`
- `server-python/app/api/notifications.py`
- `server-python/app/api/skill_reports.py`
- `server-python/app/reports/skill_reports.py`
- `server-python/app/main.py`
- `server-python/tests/test_notification_sse_fanout.py`
- `server-python/tests/test_skill_report_submit.py`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
