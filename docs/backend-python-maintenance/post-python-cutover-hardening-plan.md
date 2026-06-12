# Post Python Cutover Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Python backend after the Java-to-Python cutover so future work is maintainable without changing public API behavior.

**Architecture:** Treat `backend-python-cutover-2026-06-12` as the completed migration baseline. First add guardrails and an inventory for migration bridge SQL, then move SQL behind repository/query boundaries, then introduce SQLAlchemy ORM only for mutation-heavy aggregates where it improves transaction clarity. Preserve explicit SQL for projection-heavy reads when it remains clearer and better covered by tests.

**Tech Stack:** FastAPI, SQLAlchemy async engine, SQLAlchemy ORM where explicitly introduced, Alembic baseline already owned by Python, pytest, Vitest, Playwright.

---

## Baseline

The Java-to-Python backend migration is complete at annotated tag `backend-python-cutover-2026-06-12`.

Current observations from the post-cutover scan:

- `server-python/app/api/skills.py` is the largest backend module at about 3355 lines.
- Other large modules include `server-python/app/lifecycle/skill.py`, `server-python/app/review/query.py`, `server-python/app/admin/review_reports.py`, `server-python/app/promotion/workflow.py`, and `server-python/app/review/approval.py`.
- `server-python` currently uses SQLAlchemy async engine and `sqlalchemy.text`; no SQLAlchemy declarative ORM models are present.
- `PublishDryRunRepository` is the clearest existing local repository pattern and should guide new extraction style.
- The cutover verification baseline was:
  - `cd server-python; uv run pytest tests -q`
  - `cd web; corepack pnpm run typecheck`
  - `cd web; corepack pnpm run lint`
  - `cd web; corepack pnpm run test`
  - `cd web; corepack pnpm run test:e2e`

## Non-Goals

- Do not re-open Java route ownership. Java is reference-only after the cutover tag.
- Do not convert every SQL query to ORM. Reporting, search, and projection-heavy lists may remain explicit SQL if they stay behind repository/query functions.
- Do not change external API envelopes, HTTP statuses, message keys, auth behavior, or E2E user flows unless a milestone explicitly calls out a bug fix.
- Do not delete the Java `server/` tree as part of these milestones. Java reference retirement is a separate post-launch decision.
- Do not blindly merge upstream Java backend changes and assume Python parity. Upstream intake requires a triage note and targeted Python follow-up when Java behavior, schema, API contracts, or security rules change.

## Milestone 1: Post-Cutover Architecture Inventory And Guardrails

**Purpose:** Create a machine-checked baseline for maintainability work before moving code.

**Files:**
- Create: `docs/backend-python-maintenance/README.md`
- Create: `docs/backend-python-maintenance/results/2026-06-12-architecture-inventory.md`
- Create: `server-python/scripts/sql_inventory.py`
- Create: `server-python/tests/test_post_cutover_architecture.py`
- Modify: `server-python/AGENTS.md`

**Steps:**
- [x] Add `docs/backend-python-maintenance/README.md` defining this as the post-cutover track, separate from Java migration.
- [x] Add `server-python/scripts/sql_inventory.py` that reports `sqlalchemy.text` usage by file and flags whether it is in an API route module, domain/service module, repository/query module, migration/bootstrap module, or test.
- [x] Add `server-python/tests/test_post_cutover_architecture.py` with an allowlist of current API modules that still contain SQL bridge code. The test must fail on new API modules importing or calling `text()` unless the allowlist is updated with a reason.
- [x] Add a second architecture test that confirms no SQLAlchemy declarative ORM model exists yet. This prevents accidental partial ORM introduction before Milestone 5.
- [x] Update `server-python/AGENTS.md` with post-cutover rules:
  - New SQL must live in repository/query/helper modules, not new route handlers.
  - ORM models require a milestone plan and targeted transaction tests.
  - Projection-heavy SQL can remain explicit SQL when it is covered and isolated.
- [x] Write the result note with the current top SQL modules and large-file inventory.

**Verify:**
- `cd server-python; uv run python scripts/sql_inventory.py`
- `cd server-python; uv run pytest tests/test_post_cutover_architecture.py -q`
- `cd server-python; uv run pytest tests -q`

**Done when:** The repo has an explicit post-cutover maintenance track and guardrails prevent new route-level SQL from spreading.

## Milestone 2: Skill Read Surface Repository Boundary

**Purpose:** Reduce the blast radius of `server-python/app/api/skills.py` by moving read/query behavior behind focused modules while preserving all route behavior.

**Files:**
- Create: `server-python/app/skills/__init__.py`
- Create: `server-python/app/skills/read_repository.py`
- Create: `server-python/app/skills/file_repository.py`
- Create: `server-python/app/skills/tag_repository.py`
- Create: `server-python/app/skills/compat_repository.py`
- Modify: `server-python/app/api/skills.py`
- Modify: existing tests under `server-python/tests/test_skill_*.py`
- Create: `docs/backend-python-maintenance/results/2026-06-12-skill-read-repository-boundary.md`

**Steps:**
- [x] Move public skill search/detail/version/file metadata SQL from `app/api/skills.py` into `app/skills/read_repository.py`.
- [x] Move file content and download read helpers into `app/skills/file_repository.py`; keep storage I/O orchestration out of route handlers.
- [x] Move tag list/add/delete SQL into `app/skills/tag_repository.py`.
- [x] Move ClawHub compatibility coordinate/detail/list/resolve SQL into `app/skills/compat_repository.py`.
- [x] Leave FastAPI route functions in `app/api/skills.py` responsible only for request binding, auth principal resolution, response wrapping, and delegation.
- [x] Keep response DTO shapes and Java-compatible message keys unchanged.
- [x] Update tests only where import paths changed; do not weaken behavioral assertions.
- [x] Update the architecture allowlist so `app/api/skills.py` no longer has direct `text()` usage except temporary explicitly documented shims if needed.

**Verify:**
- `cd server-python; uv run pytest tests/test_skill_search.py tests/test_skill_detail.py tests/test_skill_versions.py tests/test_skill_version_detail.py tests/test_skill_file_metadata.py tests/test_skill_file_content.py tests/test_skill_download.py tests/test_skill_tags.py tests/test_clawhub_search.py tests/test_clawhub_skill_detail.py tests/test_clawhub_skills_list.py tests/test_clawhub_resolve.py -q`
- `cd server-python; uv run pytest tests/test_post_cutover_architecture.py -q`
- `cd server-python; uv run pytest tests -q`
- If route behavior changed or imports are broad: `cd web; corepack pnpm run test:e2e:smoke`

**Done when:** `app/api/skills.py` is a route layer, skill read SQL lives in `app/skills/*_repository.py`, and all existing skill/compat tests still pass.

## Milestone 3: Admin, Governance, And Report Query Boundaries

**Purpose:** Move admin/governance/report query SQL into explicit repository/query modules, reducing duplicated dynamic SQL and making authorization paths easier to review.

**Files:**
- Create: `server-python/app/admin/audit_repository.py`
- Create: `server-python/app/admin/user_repository.py`
- Create: `server-python/app/admin/review_report_repository.py`
- Create: `server-python/app/governance/workbench_repository.py`
- Create: `server-python/app/reports/report_repository.py`
- Modify: `server-python/app/admin/audit_logs.py`
- Modify: `server-python/app/admin/users.py`
- Modify: `server-python/app/admin/review_reports.py`
- Modify: `server-python/app/governance/workbench.py`
- Modify: `server-python/app/reports/skill_reports.py`
- Create: `docs/backend-python-maintenance/results/2026-06-12-admin-governance-query-boundaries.md`

**Steps:**
- [x] Extract admin audit-log list/count SQL into `app/admin/audit_repository.py`.
- [x] Extract admin user list/detail/role mutation SQL into `app/admin/user_repository.py`.
- [x] Extract review/report list and moderation query SQL into `app/admin/review_report_repository.py`.
- [x] Extract governance workbench counters, pending task lists, and notification summary SQL into `app/governance/workbench_repository.py`.
- [x] Extract skill report submit/read helper SQL into `app/reports/report_repository.py`.
- [x] Keep platform-role and namespace-role checks in the existing policy helpers; do not bury auth decisions inside repositories.
- [x] Remove direct `text()` calls from the corresponding API route modules where possible.
- [x] Keep dynamic SQL construction parameterized; preserve existing filter behavior exactly.

**Verify:**
- `cd server-python; uv run pytest tests/test_admin_audit_logs.py tests/test_admin_user_management.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py tests/test_governance_workbench.py tests/test_skill_report_submit.py -q`
- `cd server-python; uv run pytest tests/test_post_cutover_architecture.py -q`
- `cd server-python; uv run pytest tests -q`

**Done when:** Admin/governance/report SQL is isolated behind repository/query modules and role checks remain visible at service/route boundaries.

## Milestone 4: Lifecycle, Review, Promotion, And Publish Transaction Boundaries

**Purpose:** Make high-risk mutation workflows easier to reason about before ORM adoption.

**Files:**
- Create: `server-python/app/db/unit_of_work.py`
- Create: `server-python/app/audit/writer.py`
- Modify: `server-python/app/lifecycle/skill.py`
- Modify: `server-python/app/lifecycle/hard_delete.py`
- Modify: `server-python/app/review/approval.py`
- Modify: `server-python/app/promotion/workflow.py`
- Modify: `server-python/app/publish/orchestration.py`
- Modify: `server-python/app/publish/transaction.py`
- Create: `docs/backend-python-maintenance/results/2026-06-12-mutation-transaction-boundaries.md`

**Steps:**
- [x] Add a small `UnitOfWork` helper that wraps `engine.begin()` and exposes the active connection without changing SQL semantics.
- [x] Add an audit writer helper for common audit-log insert fields used by lifecycle/review/promotion/publish paths.
- [x] Refactor lifecycle mutation functions to use the shared transaction boundary, keeping storage cleanup after database commit.
- [x] Refactor review approval/reject/withdraw paths to use the shared transaction boundary and audit writer.
- [x] Refactor promotion submit/approve/reject paths to use the shared transaction boundary and audit writer.
- [x] Refactor publish orchestration so DB transaction, scanner handoff, search document update, and after-commit cleanup boundaries are explicit in one flow.
- [x] Keep compensation behavior unchanged; any after-commit failure behavior must remain covered by existing tests.

**Verify:**
- `cd server-python; uv run pytest tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_rerelease.py tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_hard_delete.py -q`
- `cd server-python; uv run pytest tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_review_submit.py tests/test_promotion_write.py tests/test_publish_orchestration.py tests/test_publish_transaction.py tests/test_publish_storage.py -q`
- `cd server-python; uv run pytest tests -q`
- `cd web; corepack pnpm run test:e2e:smoke`

**Done when:** Mutation transaction boundaries are explicit and shared, without public behavior changes.

## Milestone 5: Selective ORM Foundation For Mutation Aggregates

**Purpose:** Introduce SQLAlchemy ORM only where it reduces mutation complexity and transaction mistakes.

**Files:**
- Create: `server-python/app/db/models.py`
- Create: `server-python/app/db/session.py`
- Create: `server-python/tests/test_orm_mapping.py`
- Modify: `server-python/tests/test_post_cutover_architecture.py`
- Modify selected mutation modules from Milestone 4 only after mapping tests pass.
- Create: `docs/backend-python-maintenance/results/2026-06-12-selective-orm-foundation.md`

**Steps:**
- [ ] Add declarative ORM mappings for mutation-heavy tables only:
  - `skill`
  - `skill_version`
  - `review_task`
  - `promotion_request`
  - `namespace`
  - `namespace_member`
  - `user_account`
  - `api_token`
  - `audit_log`
- [ ] Do not map every projection/search/report table in this milestone.
- [ ] Add mapping tests that assert table names, primary keys, important status columns, and relationship-free basic inserts/loads against a transaction-scoped test connection.
- [ ] Add `app/db/session.py` with a narrowly scoped async session factory that can bind to the existing engine.
- [ ] Convert one low-risk lifecycle mutation helper to ORM first, behind existing public function names.
- [ ] Run the existing lifecycle/review/promotion/publish tests after the first conversion.
- [ ] Convert additional mutation helpers only when the previous helper is green and the diff remains reviewable.
- [ ] Keep read projection repositories from Milestones 2 and 3 on explicit SQL unless a specific query becomes clearer with ORM and has dedicated tests.

**Verify:**
- `cd server-python; uv run pytest tests/test_orm_mapping.py -q`
- `cd server-python; uv run pytest tests/test_post_cutover_architecture.py -q`
- `cd server-python; uv run pytest tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_confirm_publish.py tests/test_review_approve.py tests/test_promotion_write.py tests/test_publish_orchestration.py -q`
- `cd server-python; uv run pytest tests -q`

**Done when:** ORM exists as a tested, intentional tool for mutation aggregates, not as an uncontrolled rewrite of all SQL.

## Milestone 6: Test Fixture And Support Cleanup

**Purpose:** Reduce test maintenance cost after repository extraction and selective ORM adoption.

**Files:**
- Create: `server-python/tests/support/__init__.py`
- Create: `server-python/tests/support/fake_db.py`
- Create: `server-python/tests/support/builders.py`
- Modify large tests that duplicate fake connection or row-builder logic:
  - `server-python/tests/test_publish_http_validate.py`
  - `server-python/tests/test_skill_hard_delete.py`
  - `server-python/tests/test_account_merge.py`
  - `server-python/tests/test_namespace_member_mutation.py`
  - `server-python/tests/test_promotion_write.py`
  - `server-python/tests/test_api_tokens.py`
- Create: `docs/backend-python-maintenance/results/2026-06-12-test-fixture-cleanup.md`

**Steps:**
- [ ] Extract a fake async result/connection/engine toolkit from repeated test helpers.
- [ ] Add builders for common user, namespace, skill, skill version, review task, promotion request, and token rows.
- [ ] Convert one large test file at a time to the shared helpers.
- [ ] Keep each converted test's assertions equivalent; do not combine unrelated test cases.
- [ ] Remove copied helper code only after the converted file passes.
- [ ] Record before/after line counts for converted test files in the result note.

**Verify:**
- Run each converted test file directly, for example `cd server-python; uv run pytest tests/test_skill_hard_delete.py -q`
- `cd server-python; uv run pytest tests -q`

**Done when:** The largest fake-DB tests share common fixtures and future repository changes require less test boilerplate churn.

## Milestone 7: Upstream Sync And Python Parity Workflow

**Purpose:** Define a repeatable workflow for tracking future open-source upstream changes after the Python cutover.

**Files:**
- Create: `docs/backend-python-maintenance/upstream-sync-workflow.md`
- Create: `docs/backend-python-maintenance/results/2026-06-12-upstream-sync-workflow.md`
- Create: `scripts/check-upstream-backend-drift.ps1`
- Modify: `docs/backend-python-maintenance/README.md`
- Modify: `server-python/AGENTS.md`

**Steps:**
- [ ] Confirm and document the canonical open-source upstream remote. If the current `upstream` remote is not the true upstream, rename or add the correct remote before relying on drift checks.
- [ ] Define an intake cadence. Recommended default: check upstream before each hardening milestone batch and at least weekly while the project is pre-launch.
- [ ] Add `scripts/check-upstream-backend-drift.ps1` that compares a chosen upstream ref against the local cutover branch and groups changed files into:
  - Java backend contract or behavior.
  - Database migration or schema.
  - Frontend/API client expectations.
  - Docs/config/CI.
  - Scanner/CLI/other.
- [ ] Document the required triage decision for each upstream batch:
  - `port-to-python-now`: security, schema, API contract, auth/authorization, lifecycle, publish/review, or data-integrity behavior.
  - `accept-non-backend`: docs/frontend/config changes that do not affect Python runtime behavior.
  - `defer-with-reason`: non-critical Java-only implementation cleanup or behavior outside the product scope.
  - `reject`: upstream change conflicts with the Python product direction.
- [ ] Add a rule that Java behavior changes are ported by writing or updating Python tests first, then implementing Python behavior, then recording a result note.
- [ ] Add a rule that upstream Java Flyway migrations must become Python-owned Alembic/app migration changes before launch.
- [ ] Add a result note describing the workflow and the current remote state.

**Verify:**
- `powershell -ExecutionPolicy Bypass -File scripts/check-upstream-backend-drift.ps1 -BaseRef <upstream-ref> -HeadRef HEAD`
- `git diff --check`

**Done when:** Future upstream pulls have a written triage workflow and a script-assisted drift report so Python parity does not rely on memory or manual file browsing.

## Milestone 8: Full Post-Cutover Regression And Launch Readiness Note

**Purpose:** Re-run the full stack after maintainability changes and document the new baseline.

**Files:**
- Create: `docs/backend-python-maintenance/results/2026-06-12-post-cutover-hardening-regression.md`
- Modify: `server-python/README.md` if startup or testing instructions changed.
- Modify: `docs/backend-python-migration/migration-sequence-plan.md` only to add a pointer to the post-cutover maintenance plan, not to reopen migration milestones.

**Steps:**
- [ ] Run the full Python backend pytest suite.
- [ ] Run web typecheck, lint, and unit tests.
- [ ] Start a clean local Python stack and run Playwright full E2E.
- [ ] Run `git diff --check`.
- [ ] Write the regression note with exact command outcomes and any accepted residual risk.
- [ ] If all checks pass, commit the completed maintenance batch.

**Verify:**
- `cd server-python; uv run pytest tests -q`
- `cd web; corepack pnpm run typecheck`
- `cd web; corepack pnpm run lint`
- `cd web; corepack pnpm run test`
- `cd web; corepack pnpm run test:e2e`
- `git diff --check`

**Done when:** The post-cutover hardening branch has a full regression record comparable to the cutover baseline.

## Execution Rules

- Work one milestone at a time.
- Start each milestone with tests or guardrails before moving code.
- Keep public API behavior unchanged unless the milestone explicitly fixes a bug.
- Update a result note under `docs/backend-python-maintenance/results/` before commit.
- Commit after each completed and verified milestone.
- Push only after the user approves the destination branch or explicitly asks to push.

## Recommended Order

1. Milestone 1: Post-cutover architecture inventory and guardrails.
2. Milestone 2: Skill read surface repository boundary.
3. Milestone 3: Admin, governance, and report query boundaries.
4. Milestone 4: Lifecycle, review, promotion, and publish transaction boundaries.
5. Milestone 5: Selective ORM foundation for mutation aggregates.
6. Milestone 6: Test fixture and support cleanup.
7. Milestone 7: Upstream sync and Python parity workflow.
8. Milestone 8: Full post-cutover regression and launch readiness note.

This order keeps behavior stable: inventory first, route/query extraction second, transaction cleanup third, ORM only after the mutation boundaries are explicit, and upstream intake before final launch readiness.
