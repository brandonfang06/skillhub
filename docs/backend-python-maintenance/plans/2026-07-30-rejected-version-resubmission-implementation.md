# Rejected Version Resubmission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` to
> implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Allow the same owner to resubmit a rejected semantic version while
keeping the completed rejection queryable as immutable review evidence.

**Architecture:** Archive the rejected review, version metadata, file hashes,
and scanner summary before removing foreign-keyed active rows. Create the
replacement and archive linkage in the same publish transaction, then retire
old storage through the existing post-commit compensation boundary.

**Tech Stack:** FastAPI, SQLAlchemy async Core, PostgreSQL SQL migrations,
pytest, React, TypeScript, TanStack Query, Playwright.

---

### Task 1: Add the archive schema

**Files:**
- Create:
  `server-python/app/db/local_migration/20260730_01__review_attempt_archive.sql`
- Modify: migration contract tests under `server-python/tests/`

- [x] Write a failing migration contract test that requires
  `review_attempt_archive`, a unique original review-task ID, history and
  replacement indexes, JSONB snapshots, and timestamptz timestamps.
- [x] Run the focused migration test and confirm it fails because
  `20260730_01` is absent.
- [x] Add the additive local migration without changing the frozen Flyway
  `V1`-`V43` baseline or existing tables.
- [x] Run the focused migration test and migration upgrade. The isolated
  PostgreSQL runtime records `20260730_01` and exposes the 23-column
  `review_attempt_archive` table.

### Task 2: Archive rejected cleanup atomically

**Files:**
- Modify: `server-python/app/publish/replacement.py`
- Modify: `server-python/tests/test_publish_replacement.py`

- [x] Replace the rejected-reuse failure test with a failing test requiring a
  complete immutable snapshot and deletion of every review task for the
  rejected version.
- [x] Add failing cases for published/yanked/pending rejection, owner
  mismatch, status recheck, file hash capture, scanner summary capture, and no
  SQL after an ineligible state.
- [x] Implement `ArchivedReviewAttempt` and return it from
  `ReplacementCleanupResult` only for rejected replacement.
- [x] Lock and re-read the version plus rejected review, capture metadata,
  manifest, files and scanner evidence, then delete dependent active rows.
- [x] Run the replacement tests until green.

### Task 3: Link archive and replacement in publish transaction

**Files:**
- Modify: `server-python/app/publish/orchestration.py`
- Create: `server-python/app/review/archive.py`
- Modify: `server-python/tests/test_publish_orchestration.py`
- Create or modify focused archive repository tests

- [x] Write failing tests requiring archive insertion after the new
  review-task ID exists, `REJECTED_VERSION_RESUBMIT` audit creation, and
  all-or-nothing rollback.
- [x] Implement the archive repository with SQL isolated outside route
  handlers.
- [x] Insert the archive and audit row before transaction commit, linking old
  IDs to the new version and review task.
- [x] Verify storage retirement still occurs only after commit and uses
  compensation on failure.
- [x] Run orchestration and archive tests until green.

### Task 4: Change publish eligibility

**Files:**
- Modify: `server-python/app/publish/dry_run.py`
- Modify: `server-python/app/api/publish.py`
- Modify: related publish tests

- [x] Write failing tests showing an own rejected candidate passes dry-run and
  reaches replacement lookup.
- [x] Keep published/yanked, pending, coordinate conflict, and other-owner
  cases blocked before mutation.
- [x] Remove only the obsolete rejected-version 409 branch.
- [x] Run dry-run, route, transaction, and replacement tests.

### Task 5: Keep archived review detail queryable

**Files:**
- Modify: `server-python/app/review/query.py`
- Modify: `server-python/app/api/reviews.py` only if response typing requires it
- Modify: review query and route tests

- [x] Write failing tests requiring current-task lookup first and archive
  fallback by original review-task ID.
- [x] Return optional `superseded`, `artifactAvailable`,
  `replacementVersionId`, and `replacementReviewTaskId` fields.
- [x] Ensure archived attempts expose metadata and hashes but no file preview
  or download capability.
- [x] Include archived rejected attempts in paginated rejected history without
  duplicating current rows.
- [x] Run review query and route tests.

### Task 6: Update frontend behavior

**Files:**
- Modify: generated OpenAPI schema through the repository generator
- Modify: review detail/history components and tests
- Modify: publish error handling and translations
- Modify: authenticated Playwright rejected-version scenario

- [x] Generate the review API types from a focused FastAPI OpenAPI document.
  The legacy whole-app generator remains unchanged, while
  `generate-api:reviews` produces deterministic review contracts without broad
  unrelated schema churn.
- [x] Write failing unit tests for archived badges, replacement links, hidden
  file actions, and removal of the old increase-version toast.
- [x] Implement the minimal archived-attempt UI.
- [x] Replace the old 409 E2E scenario with reject, same-version resubmit, old
  detail fallback, and new pending review assertions.
- [x] Run frontend unit, typecheck, lint, build, and focused authenticated E2E,
  including desktop and mobile overflow assertions.

### Task 7: Milestone verification and result record

**Files:**
- Create:
  `docs/backend-python-maintenance/results/2026-07-30-v0.2.15-follow-up.md`

- [x] Run all focused backend tests and the migration upgrade.
- [x] Run the full backend suite.
- [x] Run frontend typecheck, lint, tests, build, and authenticated viewport
  E2E.
- [x] Run `git diff --check` and inspect the complete diff as a code reviewer.
- [x] Record commands, counts, scenario evidence, side effects, and remaining
  v0.2.15 milestones in the result document.
