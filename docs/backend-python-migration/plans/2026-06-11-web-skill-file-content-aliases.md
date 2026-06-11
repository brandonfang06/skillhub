# Web Skill File Content Alias Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for the
> implementation and `superpowers:verification-before-completion` before reporting completion.

**Goal:** Move the web skill single-file content aliases to Python:
`GET /api/web/skills/{namespace}/{slug}/versions/{version}/file` and
`GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/file`.

**Architecture:** Java `SkillController` exposes the same file content handlers through both
`/api/v1/skills` and `/api/web/skills`. Python already owns the v1 file content handlers and
storage/query behavior, so this milestone adds only web alias routes and Vite proxy ownership.

**Tech Stack:** FastAPI route aliases in `server-python/app/api/skills.py`, pytest route tests,
Vite proxy tests, migration docs.

---

## Java Parity Checklist

- API contract: covered. Java returns raw `application/octet-stream` bytes for both v1 and web
  aliases using the same controller methods.
- Authorization/session behavior: covered. Web aliases forward optional current user context exactly
  like the existing v1 Python handlers.
- Database transaction atomicity: not applicable. These are read-only content routes.
- Audit actor/timestamp fields: not applicable. Java does not write audit rows for file content
  reads.
- Storage and side effects: covered. The Python web aliases reuse the already migrated v1 storage
  reader path and do not add new side effects.
- Live verification evidence: pending until implementation.

## Tasks

- [x] Add failing FastAPI route tests proving both web aliases return raw bytes and forward
  namespace, slug, selector, path, and normalized current user.
- [x] Add failing Vite proxy tests proving both web aliases route to Python instead of Java fallback.
- [x] Add failing route-registry tests for ownership documentation and order 106 in the migration
  sequence.
- [x] Add the two FastAPI web alias decorators to the existing v1 file content handlers.
- [x] Route the two web alias patterns to Python in `web/vite.config.ts`.
- [x] Update route registry and migration sequence docs.
- [x] Run targeted pytest and Vite tests.
- [x] Run live Java/Python/proxy verification for raw byte response and content type.
- [x] Confirm no `server/` files changed and run `git diff --check`.
