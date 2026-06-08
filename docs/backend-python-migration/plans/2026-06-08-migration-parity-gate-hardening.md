# Migration Parity Gate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Java/Python behavioral parity checks a required written gate for every future
migration milestone.

**Architecture:** Add a reusable parity checklist document and wire it into the migration
entrypoints that agents already read before work: `server-python/AGENTS.md` and
`docs/backend-python-migration/migration-sequence-plan.md`. Add a lightweight pytest guard so the
checklist and required references are verified in CI-style local tests.

**Tech Stack:** Markdown migration docs, pytest doc guard, uv.

---

## Boundary

No route ownership changes.

Do not modify any file under `server/`.

## Files

Create:

- `docs/backend-python-migration/java-parity-checklist.md`
- `server-python/tests/test_migration_parity_docs.py`
- `docs/backend-python-migration/results/2026-06-08-migration-parity-gate-hardening.md`

Modify:

- `server-python/AGENTS.md`
- `docs/backend-python-migration/migration-sequence-plan.md`

## Tasks

### Task 1: Add Doc Guard Tests

- [x] Add failing tests that require:
  - `java-parity-checklist.md` exists.
  - `server-python/AGENTS.md` links to the checklist.
  - `migration-sequence-plan.md` requires parity checklist sections in plans/results.
  - the checklist names mutation-critical fields: transaction boundary, audit actor fields,
    storage side effects, authorization, and Java reference sources.

### Task 2: Add Parity Checklist

- [x] Create `docs/backend-python-migration/java-parity-checklist.md`.
- [x] Include required sections:
  - triage;
  - Java reference sources;
  - API contract parity;
  - authorization/session parity;
  - DB transaction atomicity;
  - audit/actor/timestamp fields;
  - storage and side effects;
  - live verification evidence;
  - deferral rules.

### Task 3: Wire Into Migration Entrypoints

- [x] Update `server-python/AGENTS.md`.
- [x] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [x] Require every future milestone plan/result to include Java parity checklist status.

### Task 4: Verify And Record

- [x] Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
cd server-python
uv run pytest tests/test_migration_parity_docs.py -q
```

- [ ] Run:

```powershell
git diff --check
git diff --name-only -- server
```

## Not In This Milestone

- No API route migration.
- No FastAPI route or repository changes.
- No Java source edits.
- No retroactive full parity audit of every completed milestone; this creates the required gate
  that future work must use.
