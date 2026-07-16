# Search, Namespace Delete, And Bulk Review Follow-Up

Date: 2026-07-16
Status: Completed and verified

## Scope

This follow-up covers three operator-visible behaviors:

1. Pending-only skills appearing in normal web search.
2. Namespace delete eligibility not refreshing after skills are hard-deleted.
3. Namespace-scoped bulk approve or reject for pending review tasks.

## Finding 1: Pending Skills In Search

Normal web and ClawHub search currently query `skill_search_document` without always requiring a
published latest version. The stricter `skill_version` join is only enabled for
`installable_only=True`, which is used by CLI search but not by the web search page.

The admin search rebuild also selects every active skill through a `LEFT JOIN` to
`skill.latest_version_id`. As a result, rebuilding the index can create a search document for an
active skill whose first version is still pending review. Normal web search can then return that
stale document with no published version.

An existing skill that has an older published version and a newer pending version is different:
the older published version must remain searchable, while pending metadata must not become the
public search projection.

### Proposed Fix

- Require the latest-version join to resolve to `skill_version.status = 'PUBLISHED'` for every
  normal search count and row query.
- Keep the additional `download_ready` and `yanked_at` checks for installable-only callers.
- Make full search-index rebuild skip skills without a published latest version.
- Make single-skill index upsert delete the document when the latest pointer does not resolve to a
  published version.

### Required Tests

- A pending-only skill with a stale search document is excluded from web search.
- Count and row queries use the same published-version boundary.
- A skill with an older published version and a newer pending version still returns the published
  projection.
- Search rebuild skips pending-only skills.
- CLI installable-only checks remain unchanged.

## Finding 2: Namespace Delete Eligibility

The delete action is driven by backend `canDelete`, not by a frontend-only condition. It is true
only when all of the following hold:

- the namespace type is `TEAM`;
- the current namespace role is `OWNER`;
- no `skill` row references the namespace;
- no historical `review_task` references the namespace;
- no `promotion_request` targets the namespace.

These dependency checks protect non-cascading foreign keys and governance history. Archiving a
skill or deleting only a non-final version does not remove the `skill` row. A hard-delete removes
the skill and its own review and promotion rows, but another skill's promotion request targeting
the namespace can still block namespace deletion.

There is also a frontend cache bug: successful skill hard-delete invalidates skill queries but not
`['namespaces', 'my']`. Even when the backend would recompute `canDelete=true`, the namespace page
can keep the old value until it is refreshed.

### Proposed Fix

- Invalidate `['namespaces', 'my']` after successful skill hard-delete.
- Preserve the OWNER-only and dependency-free backend deletion policy.
- Treat exposing dependency counts or a disabled-button explanation as a separate usability
  enhancement; do not delete historical review or promotion data implicitly.

### Required Tests

- Skill delete cache cleanup invalidates `['namespaces', 'my']`.
- Existing skill detail, list, star, and rating cache cleanup remains intact.
- Backend namespace dependency and OWNER checks remain unchanged.

## Finding 3: Bulk Namespace Review

The current Python backend and frontend do not implement bulk review. Only single-task approve and
reject endpoints exist. The product documentation mentions batch review, but that statement is not
backed by a current route or UI.

### Options

1. **Selected tasks with one batch request (recommended).** Add checkboxes to pending reviews and
   submit up to 100 review task IDs. The backend reuses each task's existing authorization,
   namespace-state, scan-state, optimistic-version, audit, search-index, and notification behavior.
   The response reports success or failure per task.
2. **All pending tasks in a namespace.** The backend queries every pending task in the namespace and
   applies one decision. This is faster for operators but has a larger accidental-approval blast
   radius and needs a hard cap plus explicit confirmation.
3. **Frontend fan-out to existing single-task endpoints.** This avoids a new API but creates many
   requests, weak partial-failure reporting, and inconsistent operator feedback. This option is not
   recommended.

### Recommended Contract

- Endpoint: `POST /api/web/reviews/batch-decision`.
- Request: `reviewTaskIds`, `decision` (`APPROVE` or `REJECT`), and one shared comment.
- Maximum: 100 task IDs, unique and non-empty.
- Authorization and lifecycle checks: identical to the existing single-task actions.
- Processing: independent transaction per task, preserving partial success.
- Response: one result per task with `success` and a stable error code when rejected by policy.
- Reject requires a non-blank shared comment; approve comment remains optional.
- Scanning tasks, already-decided tasks, inactive namespaces, conflicts, or unauthorized tasks fail
  individually and do not block valid tasks.

## Proposed Milestones

1. **Search and cache correctness**: fix the two confirmed bugs and run focused plus full backend and
   frontend regression tests.
2. **Bulk review backend**: add the batch contract and reuse single-task decision behavior with
   partial-result tests.
3. **Bulk review frontend**: add pending-list selection, confirmation, result summary, i18n, and
   browser-level workflow verification.

## Approved Implementation Plan

### Task 1: Enforce Published Search Boundaries

**Files:**

- Modify `server-python/tests/test_skill_search_repository.py`.
- Modify `server-python/tests/test_admin_search_rebuild.py`.
- Modify `server-python/app/skills/read_repository.py`.
- Modify `server-python/app/admin/search.py`.

- [x] Add a failing repository test proving normal web search always joins the latest version and
  requires `PUBLISHED`, while installable-only search retains readiness and yank checks.
- [x] Add failing rebuild/upsert assertions proving pending-only skills are not indexed.
- [x] Run the focused tests and confirm they fail because the published boundary is absent.
- [x] Add the minimal published-version join and rebuild/upsert filters.
- [x] Run search repository, admin search rebuild, review approval, and search API tests.

### Task 2: Refresh Namespace Delete Eligibility

**Files:**

- Modify `web/src/features/skill/skill-delete-flow.test.ts`.
- Modify `web/src/shared/hooks/skill-delete-cache.ts`.

- [x] Add a failing query-cache test proving hard-delete invalidates `['namespaces', 'my']`.
- [x] Run the focused Vitest test and confirm the namespace query remains valid.
- [x] Add the single namespace-query invalidation.
- [x] Re-run the skill delete flow and namespace page tests.

### Task 3: Add Backend Batch Review

**Files:**

- Create `server-python/app/review/batch.py`.
- Create `server-python/tests/test_review_batch.py`.
- Modify `server-python/app/api/reviews.py`.

- [x] Add failing tests for unique/non-empty IDs, 100-task cap, required reject comment, ordered
  partial results, and reuse of approve/reject behavior.
- [x] Add failing route tests for current-user metadata and response envelope.
- [x] Implement `ReviewBatchDecisionInput`, validation, sequential per-task decisions, and stable
  per-task result codes.
- [x] Add `POST /api/web/reviews/batch-decision` as a transport-only route.
- [x] Run batch, single approve/reject, notification, search-index, and route-policy tests.

### Task 4: Add Frontend Selection And Batch Actions

**Files:**

- Modify `web/src/api/types.ts`.
- Modify `web/src/api/client.ts`.
- Modify `web/src/api/client.test.ts`.
- Create `web/src/features/review/use-batch-review.ts`.
- Create `web/src/features/review/use-batch-review.test.ts`.
- Modify `web/src/pages/dashboard/namespace-reviews.tsx`.
- Modify `web/src/pages/dashboard/namespace-reviews.test.ts`.
- Modify `web/src/i18n/locales/en.json`.
- Modify `web/src/i18n/locales/zh.json`.
- Modify `web/src/i18n/locales/zh-TW.json`.

- [x] Add failing API-client and mutation-cache tests for one batch request and review/skill/
  notification invalidation.
- [x] Add failing page tests for selecting individual pending reviews, selecting the current page,
  approve confirmation, reject reason validation, and result summary copy.
- [x] Implement typed API models and the batch mutation hook.
- [x] Add pending-only checkboxes, select-current-page control, approve confirmation, reject dialog,
  and partial-result feedback.
- [x] Add English, Simplified Chinese, and Traditional Chinese translations.
- [x] Run focused frontend tests, typecheck, and lint.

### Task 5: Code Review And Full Verification

- [x] Review authorization, scan-state, namespace-state, self-review, transaction, audit,
  notification, search-index, cache, pagination, and partial-failure behavior.
- [x] Fix all critical or important findings with regression tests first.
- [x] Run `uv run pytest tests -q` in `server-python`.
- [x] Run `corepack pnpm test`, `corepack pnpm run typecheck`, `corepack pnpm run lint`, and
  `corepack pnpm run build` in `web`.
- [x] Run `git diff --check` and record exact results in this document.

## Verification Results

- Backend focused search/review tests: 24 passed, followed by 20 batch and single-review tests.
- Backend full suite: 917 passed, 1 existing Starlette TestClient deprecation warning.
- Frontend focused tests: 5 files and 41 tests passed before the final interaction additions.
- Frontend full suite: 193 files and 674 tests passed.
- Frontend typecheck: passed.
- Frontend lint: passed with zero warnings.
- Frontend production build: passed; existing runtime-config and large-chunk warnings remain.
- English, Simplified Chinese, and Traditional Chinese JSON parsing: passed.
- `git diff --check`: passed; Git only reported the repository's existing LF-to-CRLF notices.

## Review Result

No critical or important findings remain. The batch route delegates every task to the existing
single-task services, preserving authorization, scan and namespace lifecycle gates, self-review
rules, one transaction per task, audit records, notifications, and search-index updates. Expected
policy conflicts are returned per task; unexpected infrastructure or database failures still abort
the request instead of being mislabeled as policy failures.

### Deferred OpenAPI Maintenance Finding

The frontend generated schema is still the Java DTO compatibility baseline. Regenerating it from
FastAPI `/openapi.json` replaces roughly 11,500 lines and fails frontend typecheck because several
Python routes still expose generic dictionaries instead of named response models. The generated
file was therefore not changed in this milestone; the new review endpoint follows the existing
hand-written review client/type pattern. Switching code generation to FastAPI must be a separate
maintenance milestone that first adds the missing response models and contract tests.

## Non-Goals

- Do not expose pending metadata through public search.
- Do not change namespace deletion into cascading deletion.
- Do not remove review, promotion, audit, or notification history to make a namespace deletable.
- Do not bypass scan-state, namespace-state, self-review, or conflict checks in batch review.
