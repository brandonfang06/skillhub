# Vite API Default Python Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local Vite dev proxy send `/api/**` fallback traffic to Python by default while preserving only explicit Java-owned exceptions.

**Architecture:** Keep method-aware Python routing for migrated routes, add a small explicit Java exception proxy layer for Java-owned holdouts, then change the broad `/api` fallback from Java to Python. `/oauth2/**` remains Java-owned. This is a dev/hybrid cutover milestone only; it does not edit Java `server/` source.

**Tech Stack:** Vite proxy config, Vitest, FastAPI hybrid stack, migration docs.

---

## Scope

In scope:

- Update Vite proxy tests to expect `/api` fallback target `http://localhost:8081`.
- Preserve explicit Java routing for:
  - `/oauth2/**`.
  - `POST /api/v1/skills/{canonicalSlug}` one-segment non-placeholder mutation.
  - `POST /api/v1/skills/{namespace}/{slug}` and `POST /api/web/skills/{namespace}/{slug}` post-publish lifecycle holdouts not yet represented by migrated route-specific methods.
  - `GET /api/v1/skills/{skillId}/versions/{versionId}` numeric Java holdout.
  - `GET /api/v1/stars/{canonicalSlug}` and `POST /api/v1/me/skills` unmigrated compatibility holdouts.
  - `POST /api/v1/admin/audit-logs` unsupported admin mutation holdout.
- Route intentionally unmatched `/api/**` examples to Python by default so final fallback cleanup no longer depends on Java.
- Update `docs/backend-python-migration/route-registry.md`, `migration-sequence-plan.md`, and a result note.

Out of scope:

- OAuth callback/session implementation.
- Migrating the remaining Java-owned holdout endpoints themselves.
- Java `server/` edits.

## Tasks

- [x] Add failing Vite proxy tests for the cutover:
  - `/api` target becomes `http://localhost:8081`.
  - `/api/v1/search/extra` and `/api/v1/resolve/team-ai/demo` fall through to Python.
  - explicit Java holdouts still resolve to `http://localhost:8080`.
- [x] Run `npm.cmd run test -- vite.config.test.ts` and verify the new expectations fail before implementation.
- [x] Add explicit Java exception proxy entries in `web/vite.config.ts` before `/api`.
- [x] Change broad `/api` fallback target to `http://localhost:8081`.
- [x] Run Vite proxy tests and targeted Python route-registry tests.
- [x] Update migration docs and add `docs/backend-python-migration/results/2026-06-12-vite-api-default-python-cutover.md`.
- [x] Run hybrid live gate:
  - `GET http://localhost:3000/api/v1/health` returns Python health.
  - `GET http://localhost:3000/api/v1/search/extra` reaches Python fallback behavior instead of Java.
  - `GET http://localhost:3000/oauth2/authorization/github` remains Java-owned.
  - One explicit Java holdout still reaches Java.
- [x] Stop hybrid stack and verify ports are clean.
- [x] Final verification:
  - `npm.cmd run test -- vite.config.test.ts`
  - `uv run pytest tests/test_route_registry.py -q`
  - `git diff --check`
  - `git diff --name-only -- server`
