# ClawHub Delete Undelete Placeholder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move ClawHub placeholder `DELETE /api/v1/skills/{canonicalSlug}` and `POST /api/v1/skills/{canonicalSlug}/undelete` from Java fallback to Python.

**Architecture:** Implement only Java's current placeholder contract: authenticated route boundary with plain `{ ok: true }` response and no database/storage side effects. Add method-aware Vite rules for the one-segment ClawHub paths while keeping two-segment namespace/slug hard delete and nested SkillHub routes Python-owned as before.

**Tech Stack:** FastAPI routes in `server-python/app/api/skills.py`, pytest route tests, Vite proxy tests, migration docs.

---

## Scope

Move:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`

Do not change:

- `DELETE /api/v1/skills/{namespace}/{slug}` whole-skill hard delete.
- `DELETE /api/cli/v1/skills/{namespace}/{slug}` CLI delete.
- Any Java source under `server/`.
- OAuth/session behavior.
- Any real delete/restore side effects; Java currently returns a placeholder response.

## Java Parity Checklist

| Area | Planned outcome | Evidence |
| --- | --- | --- |
| Response shape | covered | Plain JSON `{ ok: true }`; no `ApiResponse` envelope. |
| Route boundary | covered | One-segment ClawHub paths only; two-segment SkillHub hard delete remains separate. |
| Auth behavior | covered | Require current mock user like other migrated authenticated ClawHub mutations. |
| Side effects | covered | No DB/storage writer is called because Java service returns a placeholder only. |
| Proxy ownership | covered | Vite routes only `DELETE /api/v1/skills/{canonicalSlug}` and `POST /api/v1/skills/{canonicalSlug}/undelete` to Python. |

## Tasks

### Task 1: Failing Python Route Tests

- [x] Update `server-python/tests/test_clawhub_skill_detail.py`.
- [x] Replace the old "mutation paths unowned" assertion with:
  - unauthenticated delete returns `401`
  - authenticated delete returns `200` with `{ ok: true }`
  - authenticated undelete returns `200` with `{ ok: true }`
  - nested two-segment `DELETE /api/v1/skills/global/demo` still does not hit this placeholder
- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py -q
```

Result: failed as expected because the placeholder routes were not implemented in Python.

### Task 2: Implement FastAPI Placeholder Routes

- [x] Add a helper in `server-python/app/api/skills.py` that requires `X-Mock-User-Id` and returns `{"ok": True}`.
- [x] Add:
  - `@router.delete("/api/v1/skills/{canonicalSlug}")`
  - `@router.post("/api/v1/skills/{canonicalSlug}/undelete")`
- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py -q
```

Result: passed.

### Task 3: Failing Proxy Tests

- [x] Update `web/vite.config.test.ts` expectations so one-segment ClawHub delete/undelete resolve to Python.
- [x] Keep two-segment hard delete expectations on Python.
- [x] Run:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: failed as expected until Vite method-aware rules were added.

### Task 4: Implement Vite Rules And Registry Docs

- [x] Add method-aware Vite rules for:
  - `DELETE /^\/api\/v1\/skills\/[^/?]+(?:\?.*)?$/`
  - `POST /^\/api\/v1\/skills\/[^/?]+\/undelete(?:\?.*)?$/`
- [x] Update `docs/backend-python-migration/route-registry.md` from Java to Python for these routes.
- [x] Update `docs/backend-python-migration/migration-sequence-plan.md` order table and current summary.
- [x] Update `server-python/tests/test_route_registry.py` to expect Python ownership for these routes and keep unmatched `/api/**` Java-owned.
- [x] Run:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: passed.

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py tests/test_route_registry.py -q
```

Expected: pass.

### Task 5: Result And Review

- [x] Write `docs/backend-python-migration/results/2026-06-11-clawhub-delete-undelete-placeholders.md`.
- [x] Run live Java/Python/proxy verification and record the result.
- [x] Run `git diff --name-only -- server` and confirm no Java files changed.
- [x] Run `git diff --check`.
- [x] Review Python route order, Vite regex specificity, and Java `ClawHubCompatAppService.deleteSkill()/undeleteSkill()` parity.
