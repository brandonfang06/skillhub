# Admin Audit Log Read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `GET /api/v1/admin/audit-logs` from Java to FastAPI with Java-compatible filtering, authorization, and page response behavior.

**Architecture:** Python will implement a focused admin audit log read service using SQLAlchemy `text()` queries and dynamic WHERE clauses that mirror `AdminAuditLogAppService`. The route is GET-only and is routed to Python by the Vite method-aware proxy; all audit writes remain owned by their source workflow routes.

**Tech Stack:** FastAPI, SQLAlchemy async text queries, pytest, Vite method-aware proxy tests, Windows hybrid Java/Python/Vite live gate.

---

## Route Ownership

Move to Python:

- `GET /api/v1/admin/audit-logs`

## Java Parity Checklist

- Controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AuditLogController.java`
- Service reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/AdminAuditLogAppService.java`
- DTO reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AuditLogItemResponse.java`
- API contract: covered. Python must return Java `PageResponse<AuditLogItemResponse>` under the standard read envelope.
- Authorization/session behavior: covered for local mock users. Java allows `AUDITOR` and `SUPER_ADMIN`; Python must reject other users.
- Database transaction atomicity: not applicable. Route is read-only.
- Audit actor/timestamp fields: not applicable. Route does not write audit records.
- Storage and side effects: not applicable.
- Live verification evidence: required before route ownership moves. Compare Java direct, Python direct, and Vite proxy responses against deterministic fixture audit logs.

## Behavioral Requirements

- Query params:
  - `page`, default `0`; Java clamps only offset with `Math.max(page, 0)` but returns the original `page`.
  - `size`, default `20`.
  - optional filters: `userId`, `action`, `requestId`, `ipAddress`, `resourceType`, `resourceId`, `startTime`, `endTime`.
- Filters:
  - trim text filters and ignore blank strings.
  - `action` is a single action filter.
  - `resourceId` compares `CAST(al.target_id AS TEXT)`.
  - `startTime` and `endTime` compare UTC instants.
- Projection fields:
  - `id`, `action`, `userId`, `username`, `details`, `ipAddress`, `requestId`, `resourceType`, `resourceId`, `timestamp`.
  - `details` is `detail_json` text when present; otherwise `targetType:targetId` if either exists; otherwise `null`.
  - `timestamp` must be Java-compatible UTC instant text.
- Ordering:
  - `ORDER BY al.created_at DESC`.

## Files

- Create: `server-python/app/admin/audit_logs.py`
- Create: `server-python/app/api/admin_audit_logs.py`
- Create: `server-python/tests/test_admin_audit_logs.py`
- Modify: `server-python/app/main.py`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `scripts/dev-hybrid.ps1`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Create result: `docs/backend-python-migration/results/2026-06-10-admin-audit-log-read-api.md`

## Tasks

- [x] Write pytest coverage for authorization, filtering, details fallback, timestamp conversion, and route envelope.
- [x] Verify tests fail because `app.admin.audit_logs` does not exist.
- [x] Implement Python admin audit log service and FastAPI route.
- [x] Add method-aware Vite proxy rule for `GET /api/v1/admin/audit-logs`.
- [x] Add Windows live gate fixture and Java/Python/proxy stable comparison.
- [x] Update route registry and migration sequence plan.
- [x] Run narrow Python tests, Vite proxy tests, Windows live gate, `git diff --name-only -- server`, and `git diff --check`.
- [x] Write the result document.
- [x] Commit and push to `origin/dev`.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_audit_logs.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-audit-log-smoke`
- `git diff --name-only -- server`
- `git diff --check`
