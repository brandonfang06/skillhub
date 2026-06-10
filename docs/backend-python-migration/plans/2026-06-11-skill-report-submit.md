# Skill Report Submit Migration Plan

## Summary

Move user-facing skill report submission routes to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/reports`
- `POST /api/web/skills/{namespace}/{slug}/reports`

This closes the submit side of the skill-report governance workflow after admin report list and
resolve/dismiss ownership already moved to Python.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/skills/{namespace}/{slug}/reports`
- `POST /api/web/skills/{namespace}/{slug}/reports`

Unchanged ownership:

- Admin report list/resolve/dismiss remain Python-owned.
- Governance inbox/notifications remain Python-owned where already migrated.
- OAuth, session bootstrap, direct login, bearer-token authentication filters, and scope
  enforcement remain Java-owned.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillReportController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/report/SkillReportService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/report/SkillReport.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillReportSubmitRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillReportMutationResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/listener/NotificationEventListener.java`

Expected behavior:

- Requires an authenticated current user.
- Resolves `namespace` after stripping a leading `@`.
- Resolves the target skill with published preference.
- Rejects blank `reason` with `error.skill.report.reason.required`.
- Rejects inactive or hidden skills with `error.skill.report.unavailable`.
- Rejects self-report with `error.skill.report.self`.
- Rejects duplicate pending reports for the same `(skill_id, reporter_id)` with
  `error.skill.report.duplicate`.
- Stores `reason.trim()`.
- Stores `details.trim()` or `null` when blank/missing.
- Inserts a pending `skill_report`.
- Writes `REPORT_SKILL` audit with detail JSON `{"reportId":<id>}`.
- Sends `REPORT_SUBMITTED` legacy notifications to platform `SKILL_ADMIN` and `SUPER_ADMIN`
  recipients using Java-compatible body fields.
- Returns Java envelope with `response.success.created` semantics and
  `data = { reportId, status }`.

## Implementation Scope

Allowed edits:

- `server-python/app/reports/skill_reports.py`
- `server-python/app/api/skill_reports.py`
- `server-python/app/main.py`
- `server-python/tests/test_skill_report_submit.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Schema changes.
- OAuth/session/direct-login/local-login changes.
- Admin report mutation behavior unrelated to submit.

## Test Plan

- Unit/service tests:
  - successful submit inserts `skill_report`, audit log, and notifications;
  - trims reason/details and normalizes blank details to `null`;
  - rejects blank reason, self-report, duplicate pending report, hidden/inactive skill;
  - strips leading `@` namespace slug.
- Route tests:
  - both v1 and web aliases return Java-compatible envelope;
  - missing auth returns `401`.
- Vite tests:
  - report submit aliases route to Python;
  - adjacent skill detail/download routes keep their existing ownership.
- Windows live gate:
  - compare Java/Python/proxy response and DB side effects for isolated fixture skills;
  - compare duplicate/self/blank-reason status parity;
  - run Playwright smoke.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_skill_report_submit.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-skill-report-submit-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing service/route/Vite/hybrid-script tests.
- [x] Implement Python skill-report submit service and routes.
- [x] Move Vite proxy ownership for report submit routes only.
- [x] Add Windows live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.
