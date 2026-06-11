# API Java Exception Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining Vite dev proxy Java exceptions for `/api/**` so local hybrid development sends all API traffic to Python; keep only `/oauth2/**` on Java.

**Architecture:** Delete the method-aware Java exception rules from `web/vite.config.ts`, keep Python-owned method-aware rules and the broad `/api` Python fallback, and update tests/docs to lock the new boundary. Previously Java-owned unsupported holdouts now resolve through Python's existing explicit routes or fallback behavior instead of Java sidecar behavior.

**Tech Stack:** Vite proxy config, Vitest, FastAPI route-registry tests, hybrid live gate.

---

## Scope

In scope:

- Remove all `target: 'http://localhost:8080'` method-aware rules for `/api/**`.
- Keep `/oauth2/**` routed to Java.
- Add/adjust Vite tests so:
  - No method-aware API rule targets Java.
  - No static `/api` proxy entry targets Java.
  - Former holdout examples resolve to Python via method-aware Python rules or `/api` fallback.
  - OAuth remains Java-owned.
- Update migration docs to replace explicit Java API exception rows with Python fallback/unsupported ownership.
- Add a result note with RED/GREEN, live gate, and final verification evidence.

Out of scope:

- Implementing OAuth callbacks/session establishment in Python.
- Adding new business behavior for unsupported/method-mismatched API paths.
- Java `server/` edits.

## Tasks

- [x] Add failing Vite tests for the final API cutover:
  - Assert method-aware rules have no `http://localhost:8080` target for `/api` patterns.
  - Assert former holdouts such as `POST /api/v1/skills/demo`, `GET /api/v1/stars/agent-helper`, `POST /api/v1/me/skills`, and `POST /api/v1/admin/audit-logs` resolve to Python.
  - Assert `/oauth2/authorization/github` remains Java.
- [x] Run `npm.cmd run test -- vite.config.test.ts` and verify the new expectations fail before implementation.
- [x] Remove the `/api/**` Java method-aware exception rules from `web/vite.config.ts`.
- [x] Run Vite proxy tests and route-registry tests.
- [x] Update `docs/backend-python-migration/route-registry.md`, `migration-sequence-plan.md`, and `server-python/tests/test_route_registry.py`.
- [x] Add `docs/backend-python-migration/results/2026-06-12-api-java-exception-removal.md`.
- [x] Run hybrid live gate:
  - `GET /api/v1/health` through Vite returns Python health.
  - Former Java holdouts through Vite match Python direct status.
  - `/oauth2/authorization/github` through Vite matches Java direct status.
- [x] Stop hybrid stack and verify ports are clean.
- [x] Final verification:
  - `npm.cmd run test -- vite.config.test.ts`
  - `uv run pytest tests/test_route_registry.py -q`
  - `git diff --check`
  - `git diff --name-only -- server`
