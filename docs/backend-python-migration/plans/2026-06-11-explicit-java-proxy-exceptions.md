# Explicit Java Proxy Exceptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the remaining Java-owned API proxy exceptions explicit so final proxy cleanup cannot accidentally route them to Python.

**Architecture:** Keep the current Vite proxy behavior unchanged, but add route-registry rows and pytest guard coverage for the Java-owned ClawHub delete/undelete and fallback paths that are still intentionally served by Java. This is a documentation and safety-net milestone after named route migration, not a behavior migration.

**Tech Stack:** Markdown migration docs, pytest route-registry guard tests, existing Vite proxy tests.

---

## Scope

Change:

- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `server-python/tests/test_route_registry.py`
- `docs/backend-python-migration/results/2026-06-11-explicit-java-proxy-exceptions.md`

Do not change:

- Java source under `server/`
- Runtime proxy behavior in `web/vite.config.ts`
- Python route behavior
- OAuth/session implementation

## Java Exception Matrix

| Method | Path | Owner | Reason |
| --- | --- | --- | --- |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java | ClawHub placeholder delete response remains Java-owned and is distinct from two-segment namespace/slug hard delete. |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java | ClawHub placeholder undelete response remains Java-owned. |
| * | `/api/**` unmatched paths | java | Fallback for unregistered or intentionally unmigrated API paths until final cutover. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |

## Tasks

### Task 1: Add Failing Registry Guard

- [x] Create `server-python/tests/test_route_registry.py`.
- [x] Assert `route-registry.md` contains explicit Java rows for:
  - `DELETE /api/v1/skills/{canonicalSlug}`
  - `POST /api/v1/skills/{canonicalSlug}/undelete`
  - `* /api/** unmatched`
  - `* /oauth2/**`
- [x] Assert `migration-sequence-plan.md` records the explicit Java exception milestone.
- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_route_registry.py -q
```

Result: failed as expected because the explicit Java rows and milestone note did not exist yet.

### Task 2: Update Registry And Plan Docs

- [x] Add explicit Java exception rows to `route-registry.md` before the broad fallback rows.
- [x] Update `migration-sequence-plan.md` with a new completed order for explicit Java proxy exceptions.
- [x] Update the current next-step summary to say final proxy cleanup is blocked until these explicit Java exceptions are either migrated or intentionally preserved.
- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_route_registry.py -q
```

Result: passed.

### Task 3: Verify Existing Proxy Behavior Still Matches

- [x] Run:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: passed; this confirms the milestone did not alter runtime proxy behavior.

- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_hybrid_makefile.py tests/test_route_registry.py -q
```

Result: passed.

### Task 4: Result And Review

- [x] Write `docs/backend-python-migration/results/2026-06-11-explicit-java-proxy-exceptions.md`.
- [x] Run `git diff --name-only -- server` and confirm no Java files changed.
- [x] Run `git diff --check`.
- [x] Review `route-registry.md` against `web/vite.config.test.ts` and Java `ClawHubCompatController` to ensure the explicit Java exceptions match live proxy expectations.
