# Admin Review And Report List Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move admin list reads for skill reports and profile review requests to FastAPI while leaving admin mutation routes Java-owned.

**Architecture:** Implement focused Python read services with SQLAlchemy `text()` queries that mirror the Java app services and query repositories. Vite uses method-aware GET-only ownership rules so `POST` resolve/dismiss/approve/reject routes remain Java-owned.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, pytest, Vite proxy tests, Windows hybrid Java/Python/Vite live gate.

---

## Route Ownership

Move to Python:

- `GET /api/v1/admin/skill-reports`
- `GET /api/v1/admin/profile-reviews`

Keep Java-owned:

- `POST /api/v1/admin/skill-reports/{reportId}/resolve`
- `POST /api/v1/admin/skill-reports/{reportId}/dismiss`
- `POST /api/v1/admin/profile-reviews/{id}/approve`
- `POST /api/v1/admin/profile-reviews/{id}/reject`

## Java Parity Checklist

- Skill report controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminSkillReportController.java`
- Skill report service reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/AdminSkillReportAppService.java`
- Skill report query reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/JpaAdminSkillReportQueryRepository.java`
- Profile review controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminProfileReviewController.java`
- Profile review service reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/AdminProfileReviewAppService.java`
- Profile review query reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/JpaProfileReviewQueryRepository.java`
- API contract: return Java `PageResponse` under standard read envelope.
- Authorization/session behavior:
  - skill report list requires `SKILL_ADMIN` or `SUPER_ADMIN`.
  - profile review list requires `USER_ADMIN` or `SUPER_ADMIN`.
- Database transaction atomicity: not applicable. Routes are read-only.
- Audit actor/timestamp fields: not applicable. Routes do not write audit records.
- Storage and side effects: not applicable.
- Live verification evidence: required before ownership moves. Compare Java direct, Python direct, and Vite proxy responses against deterministic DB fixtures.

## Behavioral Requirements

### Skill Report List

- Query params: `status`, `page=0`, `size=20`.
- Blank `status` defaults to `PENDING`.
- Status is trimmed and uppercased.
- Invalid status returns Java-compatible bad request behavior.
- Page response returns the effective Spring page number and size.
- Rows are selected by `skill_report.status`.
- Projection fields:
  - `id`, `skillId`, `namespace`, `skillSlug`, `skillDisplayName`, `reporterId`, `reason`, `details`, `status`, `handledBy`, `handleComment`, `createdAt`, `handledAt`.
- Skill context is nullable when the related skill no longer exists, matching `JpaAdminSkillReportQueryRepository`.

### Profile Review List

- Query params: `status`, `page=0`, `size=20`, `sortDirection=DESC`.
- Blank `status` defaults to `PENDING`.
- Status is trimmed and uppercased.
- Invalid status returns Java-compatible bad request behavior.
- Sort field:
  - `created_at` for `PENDING`.
  - `reviewed_at` for non-`PENDING`.
- Sort direction follows Java `Sort.Direction.fromOptionalString(...).orElse(DESC)`.
- Tie-breaker sort uses `id` in the same direction.
- Projection fields:
  - `id`, `userId`, `username`, `currentDisplayName`, `requestedDisplayName`, `status`, `machineResult`, `reviewerId`, `reviewerName`, `reviewComment`, `createdAt`, `reviewedAt`.
- `username` is submitter display name or `userId` if missing.
- `currentDisplayName` prefers `old_values.displayName`, then submitter display name.
- `requestedDisplayName` is `changes.displayName`.
- Invalid JSON snapshots are tolerated as empty maps.

## Files

- Create: `server-python/app/admin/review_reports.py`
- Create: `server-python/app/api/admin_review_reports.py`
- Create: `server-python/tests/test_admin_review_reports.py`
- Modify: `server-python/app/main.py`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `scripts/dev-hybrid.ps1`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Create result: `docs/backend-python-migration/results/2026-06-10-admin-review-report-list-reads.md`

## Tasks

- [x] Write pytest coverage for both list services, role guards, invalid statuses, JSON fallback behavior, route envelopes, and GET-only route ownership.
- [x] Verify tests fail because `app.admin.review_reports` does not exist.
- [x] Implement Python read services and FastAPI routes.
- [x] Add method-aware Vite proxy rules for the two GET routes only.
- [x] Add Windows live gate fixture and Java/Python/proxy stable comparison.
- [x] Update route registry and migration sequence plan.
- [x] Run narrow Python tests, Vite proxy tests, Windows live gate, `git diff --name-only -- server`, and `git diff --check`.
- [x] Write the result document.
- [x] Commit and push to `origin/dev`.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_review_reports.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-review-report-smoke`
- `git diff --name-only -- server`
- `git diff --check`
