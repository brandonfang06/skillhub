# Governance Workbench Read APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the governance workbench read APIs from Java to FastAPI while preserving Java-visible response contracts and keeping governance notification mark-read Java-owned.

**Architecture:** Python will implement a focused governance read service over SQLAlchemy `text()` queries, matching Java's `GovernanceWorkbenchAppService` and `JpaGovernanceQueryRepository` projections. Vite will route only the GET workbench reads to Python on both `/api/v1` and `/api/web`; `POST /governance/notifications/{id}/read` remains Java-owned.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, pytest, Vite method-aware proxy tests, Windows hybrid Java/Python/Vite live gate.

---

## Route Ownership

Move to Python:

- `GET /api/v1/governance/summary`
- `GET /api/web/governance/summary`
- `GET /api/v1/governance/inbox`
- `GET /api/web/governance/inbox`
- `GET /api/v1/governance/activity`
- `GET /api/web/governance/activity`
- `GET /api/v1/governance/notifications`
- `GET /api/web/governance/notifications`

Keep Java-owned:

- `POST /api/v1/governance/notifications/{id}/read`
- `POST /api/web/governance/notifications/{id}/read`

## Java Parity Checklist

- Controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/GovernanceController.java`
- Service reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/GovernanceWorkbenchAppService.java`
- Query reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/JpaGovernanceQueryRepository.java`
- DTO references:
  - `GovernanceSummaryResponse`
  - `GovernanceInboxItemResponse`
  - `GovernanceActivityItemResponse`
  - `GovernanceNotificationResponse`
- API contract: covered. Python must return the same envelope message, page shape, item fields, timestamps, and null behavior.
- Authorization/session behavior: covered for local mock users through `X-Mock-User-Id`. Governance reads require an authenticated user. Platform roles are read from `user_role_binding`; namespace OWNER/ADMIN roles are read from `namespace_member`.
- Database transaction atomicity: not applicable. These routes are read-only.
- Audit actor/timestamp fields: not applicable. These routes do not write audit records.
- Storage and side effects: not applicable. These routes do not touch storage.
- Live verification evidence: required before route ownership moves. Compare Java direct, Python direct, and Vite proxy responses against deterministic fixtures.

## Behavioral Requirements

- Summary:
  - `pendingReviews`: visible pending review total. `SKILL_ADMIN`/`SUPER_ADMIN` sees all pending reviews; namespace OWNER/ADMIN sees only pending reviews in managed namespaces.
  - `pendingPromotions`: only platform governance roles see pending promotions; other users get `0`.
  - `pendingReports`: only platform governance roles see pending reports; other users get `0`.
  - `unreadNotifications`: count unread `user_notification` rows for current user.
- Inbox:
  - Combines pending reviews, promotions, and reports.
  - `type` filter is case-insensitive for `REVIEW`, `PROMOTION`, `REPORT`; blank or missing includes all.
  - Platform governance roles see all three types.
  - Namespace OWNER/ADMIN sees visible pending reviews only.
  - Items are sorted by `timestamp` descending with nulls last, then paginated after merge.
  - Response shape is Java `PageResponse`: `{ items, total, page, size }`.
- Activity:
  - `SKILL_ADMIN`, `SUPER_ADMIN`, and `AUDITOR` can read activity.
  - Other users receive an empty page with requested `page` and `size`.
  - Activity actions match Java's `ACTIVITY_ACTIONS` set and order by audit log `created_at DESC`.
  - Details are `detail_json` when present; otherwise `targetType:targetId` if either exists.
- Governance notifications:
  - Reads from the legacy `user_notification` table, not the newer `notification` table.
  - Filters current user's rows only, ordered by `created_at DESC`.
  - Response item fields: `id`, `category`, `entityType`, `entityId`, `title`, `bodyJson`, `status`, `createdAt`, `readAt`.

## Files

- Create: `server-python/app/governance/workbench.py`
- Create: `server-python/app/api/governance.py`
- Create: `server-python/tests/test_governance_workbench.py`
- Modify: `server-python/app/main.py`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `scripts/dev-hybrid.ps1`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Create result: `docs/backend-python-migration/results/2026-06-10-governance-workbench-read-apis.md`

## Tasks

- [ ] Write pytest coverage for summary, inbox merge/scope, activity authorization, and legacy governance notification projection.
- [ ] Verify the new tests fail because `app.governance.workbench` does not exist.
- [ ] Implement the Python governance workbench service and FastAPI routes.
- [ ] Add method-aware Vite proxy rules for the migrated GET routes only.
- [ ] Add Windows live gate fixtures and Java/Python/proxy comparison for governance reads.
- [ ] Update route registry and migration sequence plan.
- [ ] Run narrow Python tests, Vite proxy tests, Windows live gate, `git diff --name-only -- server`, and `git diff --check`.
- [ ] Write the result document.
- [ ] Commit and push to `origin/dev`.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_governance_workbench.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-governance-workbench-smoke`
- `git diff --name-only -- server`
- `git diff --check`
