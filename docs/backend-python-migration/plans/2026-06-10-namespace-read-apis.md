# Namespace Read APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checklist syntax for tracking.

**Goal:** Move the first namespace dashboard read APIs to FastAPI while keeping namespace mutations and member-management routes Java-owned.

**Architecture:** Python will add a focused namespace read module backed by SQLAlchemy `text` queries. Vite will route only the three GET read paths to Python; all namespace POST/PUT/DELETE routes, member routes, and lifecycle governance actions remain Java-owned.

**Tech Stack:** FastAPI, SQLAlchemy async engine with explicit SQL, uv/pytest, Vite method-aware proxy.

---

## Route Ownership

Move to Python:

- `GET /api/v1/namespaces`
- `GET /api/web/namespaces`
- `GET /api/v1/me/namespaces`
- `GET /api/web/me/namespaces`
- `GET /api/v1/namespaces/{slug}`
- `GET /api/web/namespaces/{slug}`

Remain Java-owned:

- `POST /api/v1/namespaces`, `POST /api/web/namespaces`
- `PUT /api/v1/namespaces/{slug}`, `PUT /api/web/namespaces/{slug}`
- `DELETE /api/v1/namespaces/{slug}`, `DELETE /api/web/namespaces/{slug}`
- namespace lifecycle routes: freeze, unfreeze, archive, restore
- namespace member routes: members, member-candidates, transfer-ownership

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NamespaceController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/NamespacePortalQueryAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceAccessPolicy.java`
- DTOs: `NamespaceResponse`, `MyNamespaceResponse`, `PageResponse`

Checklist:

- API contract: covered. Preserve Java `ApiResponse` envelope and DTO field names.
- Authorization/session: covered for local migration bridge. Require `X-Mock-User-Id` and active local user, then derive namespace roles from `namespace_member`.
- Database transaction atomicity: not applicable. Read-only SQL.
- Audit actor/timestamp fields: not applicable. No writes.
- Storage/side effects: not applicable.
- Live verification: covered by a Windows Java/Python/Vite comparison gate.

## Contract Notes

- `listNamespaces` returns only ACTIVE namespaces where the caller has any namespace role, sorted by slug and paginated.
- `listMyNamespaces` returns all namespaces where the caller has any namespace role, sorted by slug. It includes role and lifecycle capability flags.
- `getNamespace` returns a namespace only when the caller is a member. Archived namespaces are visible only to members; non-members see Java-compatible not-found behavior for archived slugs.
- Capability flags follow Java `NamespaceAccessPolicy`:
  - GLOBAL namespaces are immutable.
  - TEAM ACTIVE OWNER/ADMIN can freeze.
  - TEAM FROZEN OWNER/ADMIN can unfreeze.
  - TEAM non-ARCHIVED OWNER can archive.
  - TEAM ARCHIVED OWNER can restore.
  - TEAM OWNER can delete only when no skill, review task, or promotion request depends on the namespace.

## Implementation Tasks

- [x] Write failing Python tests for namespace read service and routes.
- [x] Implement `server-python/app/namespace/read.py`.
- [x] Add FastAPI namespace routes and include the router.
- [x] Add Vite GET-only proxy rules and tests.
- [x] Add Windows live gate in `scripts/dev-hybrid.ps1` and hybrid makefile test coverage.
- [x] Update route registry, sequence plan, and result docs.
- [x] Run narrow pytest/Vitest/live gate checks.
- [x] Confirm no `server/` changes, commit, and push.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_read.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-read-smoke`
- `git diff --name-only -- server`
