# Admin Review And Report Mutations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move admin skill report and profile review mutation routes to FastAPI with Java-compatible state transitions, audit logs, and notification side effects.

**Architecture:** Extend the existing Python admin review/report module with transactional write functions. Each mutation runs in one SQLAlchemy transaction, validates current state before updates, writes the same audit records as Java, and keeps Vite route ownership method-aware.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, pytest, Vite proxy tests, Windows hybrid Java/Python/Vite live gate.

---

## Route Ownership

Move to Python:

- `POST /api/v1/admin/skill-reports/{reportId}/resolve`
- `POST /api/v1/admin/skill-reports/{reportId}/dismiss`
- `POST /api/v1/admin/profile-reviews/{id}/approve`
- `POST /api/v1/admin/profile-reviews/{id}/reject`

Already Python-owned:

- `GET /api/v1/admin/skill-reports`
- `GET /api/v1/admin/profile-reviews`

## Java Parity Checklist

- Skill report controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminSkillReportController.java`
- Skill report service reference: `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/report/SkillReportService.java`
- Profile review controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminProfileReviewController.java`
- Profile review service reference: `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/user/ProfileReviewService.java`
- Skill governance side effects reference: migrated Python admin skill governance functions and Java `SkillGovernanceService`.
- API contract:
  - skill report mutations return `SkillReportMutationResponse`: `{ id, status }`.
  - profile review mutations return `ProfileReviewMutationResponse`: `{ id, status }`.
  - all routes use Java `response.success.updated` message (`更新成功`).
- Authorization/session behavior:
  - skill report mutations require `SKILL_ADMIN` or `SUPER_ADMIN`.
  - `RESOLVE_AND_HIDE` additionally requires `SUPER_ADMIN`.
  - profile review mutations require `USER_ADMIN` or `SUPER_ADMIN`.
- Database transaction atomicity: required. State update, audit log, notification, and optional skill hide/archive side effects must commit or rollback together.
- Audit parity:
  - skill report resolve: `RESOLVE_SKILL_REPORT` on `SKILL_REPORT`.
  - skill report dismiss: `DISMISS_SKILL_REPORT` on `SKILL_REPORT`.
  - profile approve: `PROFILE_REVIEW_APPROVE` on `PROFILE_CHANGE_REQUEST`.
  - profile reject: `PROFILE_REVIEW_REJECT` on `PROFILE_CHANGE_REQUEST`, `detail_json` contains comment.
- Notification parity:
  - skill report resolve inserts legacy `user_notification` with category `REPORT`, entity type `SKILL_REPORT`, title `Report handled`, body `{"status":"RESOLVED"}`.
  - skill report dismiss inserts title `Report dismissed`, body `{"status":"DISMISSED"}`.
  - profile review mutations do not create notifications in Java.
- Live verification evidence: required before ownership moves. Compare Java direct, Python direct, and Vite proxy effects against deterministic cloned fixtures.

## Behavioral Requirements

### Skill Report Resolve

- Request body is optional.
- `disposition` defaults to `RESOLVE_ONLY`.
- `disposition` is trimmed and uppercased before enum mapping.
- Supported dispositions: `RESOLVE_ONLY`, `RESOLVE_AND_HIDE`, `RESOLVE_AND_ARCHIVE`.
- Missing report returns `error.skill.report.notFound`.
- Non-pending report returns `error.skill.report.alreadyHandled`.
- `comment` is trimmed; blank comments become `null`.
- `RESOLVE_AND_HIDE`:
  - requires `SUPER_ADMIN`.
  - sets `skill.hidden = true`, `hidden_by`, `hidden_at`, `updated_by`, `updated_at`.
  - writes Java-compatible `HIDE_SKILL` audit.
- `RESOLVE_AND_ARCHIVE`:
  - sets `skill.status = ARCHIVED`, `updated_by`, `updated_at`.
  - writes Java-compatible `ARCHIVE_SKILL` audit.
- Always transitions report to `RESOLVED`, sets `handled_by`, `handle_comment`, `handled_at`, writes `RESOLVE_SKILL_REPORT`, and inserts user notification.

### Skill Report Dismiss

- Request body is optional.
- Missing report returns `error.skill.report.notFound`.
- Non-pending report returns `error.skill.report.alreadyHandled`.
- `comment` is trimmed; blank comments become `null`.
- Transitions report to `DISMISSED`, sets `handled_by`, `handle_comment`, `handled_at`, writes `DISMISS_SKILL_REPORT`, and inserts user notification.

### Profile Review Approve

- Missing request returns `error.profileReview.notFound`.
- Non-pending request returns `error.profileReview.notPending`.
- Parses `changes` JSON and applies only `displayName` to `user_account`, matching Java's current `applyChanges`.
- If target user is missing, returns `error.user.notFound`.
- Transitions request to `APPROVED`, sets `reviewer_id`, `reviewed_at`, writes `PROFILE_REVIEW_APPROVE`.

### Profile Review Reject

- Request body requires `comment`, matching Java validation.
- Missing request returns `error.profileReview.notFound`.
- Non-pending request returns `error.profileReview.notPending`.
- Transitions request to `REJECTED`, sets `reviewer_id`, `reviewed_at`, `review_comment`, and writes `PROFILE_REVIEW_REJECT` with comment detail JSON.

## Files

- Modify: `server-python/app/admin/review_reports.py`
- Modify: `server-python/app/api/admin_review_reports.py`
- Create: `server-python/tests/test_admin_review_report_mutations.py`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `scripts/dev-hybrid.ps1`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Create result: `docs/backend-python-migration/results/2026-06-10-admin-review-report-mutations.md`

## Tasks

- [x] Write pytest coverage for report resolve/dismiss DB state, notifications, audit logs, profile approve/reject state, display-name application, role guards, invalid disposition, and route envelopes.
- [x] Verify tests fail because mutation functions/routes do not exist.
- [x] Implement transactional Python write functions.
- [x] Add FastAPI POST routes with Java-compatible messages and request handling.
- [x] Expand Vite method-aware proxy ownership for the four POST routes.
- [x] Add Windows live gate fixture and Java/Python/proxy DB/audit/notification comparison.
- [x] Update route registry and migration sequence plan.
- [x] Run narrow Python tests, Vite proxy tests, Windows live gate, `git diff --name-only -- server`, and `git diff --check`.
- [x] Write the result document.
- [ ] Commit and push to `origin/dev`.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_review_report_mutations.py tests/test_admin_review_reports.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-review-report-mutation-smoke`
- `git diff --name-only -- server`
- `git diff --check`
