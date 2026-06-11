# Admin Search Rebuild API Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for the
> implementation and `superpowers:verification-before-completion` before reporting completion.

**Goal:** Move `POST /api/v1/admin/search/rebuild` to Python.

**Architecture:** The Java endpoint is a SUPER_ADMIN-only maintenance route. Python will keep the
route narrow: rebuild `skill_search_document` rows from ACTIVE skills and latest-version metadata,
then write the Java-compatible `REBUILD_SEARCH_INDEX` audit row. This milestone does not add
background label/search side-effect rebuilding.

**Tech Stack:** FastAPI route, SQLAlchemy `text`, pytest fake-connection tests, Vite proxy tests,
migration docs.

---

## Java Parity Checklist

- API contract: covered. Java returns an `ApiResponse<Void>` success envelope with message key
  `response.success.updated` and `data = null`.
- Authorization/session behavior: covered. Java requires `SUPER_ADMIN`; Python will use the local
  mock current-user bridge and reject unauthenticated or non-super-admin users.
- Database transaction atomicity: covered. Rebuild and audit insert run in one database transaction.
- Audit actor/timestamp fields: covered. Python writes `REBUILD_SEARCH_INDEX`, target type
  `SEARCH_INDEX`, no target id, request id, client IP, user agent, and `{"scope":"ALL"}` details.
- Storage and side effects: not applicable. No object storage access.
- Live verification evidence: pending until implementation.

## Tasks

- [x] Add failing Python route tests for auth rejection, successful Java envelope, and writer call.
- [x] Add failing Python DB helper tests for rebuilding ACTIVE skills, metadata/label keyword
  extraction, upsert, and audit.
- [x] Add failing Vite proxy test for `POST /api/v1/admin/search/rebuild` routing to Python.
- [x] Add failing route-registry/sequence tests for order 107.
- [x] Implement Python search rebuild helper and route.
- [x] Register the route in `server-python/app/main.py`.
- [x] Route the admin search rebuild method to Python in `web/vite.config.ts`.
- [x] Update migration docs and write result notes.
- [x] Run targeted pytest and Vite tests.
- [x] Run live Java/Python/proxy verification.
- [x] Confirm no `server/` files changed and run `git diff --check`.
