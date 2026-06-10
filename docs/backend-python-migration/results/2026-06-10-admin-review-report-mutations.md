# Admin Review And Report Mutations Result

## Summary

Moved the admin report/profile review mutation routes to FastAPI:

- `POST /api/v1/admin/skill-reports/{reportId}/resolve`
- `POST /api/v1/admin/skill-reports/{reportId}/dismiss`
- `POST /api/v1/admin/profile-reviews/{id}/approve`
- `POST /api/v1/admin/profile-reviews/{id}/reject`

The route ownership is now Python for both the list reads and the mutation actions in this admin review/report surface.

## Behavior Implemented

- Skill report resolve/dismiss:
  - Preserves `SKILL_ADMIN`/`SUPER_ADMIN` guard.
  - Preserves `RESOLVE_AND_HIDE` extra `SUPER_ADMIN` guard.
  - Preserves pending-only transitions and Java error keys.
  - Writes `RESOLVE_SKILL_REPORT` / `DISMISS_SKILL_REPORT` audit logs.
  - Writes legacy `user_notification` rows with `REPORT` category and `UNREAD` status.
  - Applies `RESOLVE_AND_HIDE` and `RESOLVE_AND_ARCHIVE` skill side effects in the same transaction.
- Profile review approve/reject:
  - Preserves `USER_ADMIN`/`SUPER_ADMIN` guard.
  - Preserves pending-only transitions and Java error keys.
  - Applies only `displayName` from `changes` during approve.
  - Writes `PROFILE_REVIEW_APPROVE` / `PROFILE_REVIEW_REJECT` audit logs.

## Live Gate Findings

- First live run failed on Python profile approve because `profile_change_request.reviewed_at` is a timestamp without time zone. Fixed by binding naive UTC timestamps for profile review mutations.
- Second live run failed on `RESOLVE_AND_HIDE` audit detail. Java trims `skill_report.handle_comment`, but keeps the raw request comment in the `HIDE_SKILL` audit reason. Fixed Python to preserve the raw audit reason while still trimming `handle_comment`.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_review_report_mutations.py tests/test_admin_review_reports.py tests/test_hybrid_makefile.py -q`
  - Passed: 16 tests.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: 34 tests.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-review-report-mutation-smoke`
  - Passed.
  - Compared Java direct, Python direct, and Vite proxy for resolve, dismiss, approve, and reject.
  - Compared response envelopes, DB state, audit logs, and report notifications.

## Risks And Follow-Up

- `RESOLVE_AND_ARCHIVE` is covered by unit-level side-effect logic but was not part of the live gate matrix; the live gate exercises `RESOLVE_AND_HIDE`, dismiss, approve, and reject.
- Admin password reset remains Java-owned because it depends on local-auth reset token generation and operator/email behavior.
- Skill label attach/detach and auth/token surfaces remain Java-owned.
