# Review Requested Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the review-bound requested skill visibility to authorized namespace and platform reviewers without changing lifecycle behavior.

**Architecture:** Extend the review detail contract with the version snapshot stored in `skill_version.requested_visibility` and an effective approval value calculated by the existing post-submission visibility-audit rule. Render the requested value with localized labels and a neutral legacy fallback, show the approval value only when it differs, and leave review list responses unchanged.

**Review correction:** Code review found that approval intentionally uses current skill visibility only when an audited visibility update occurred after submission. The detail contract therefore also exposes `approvalVisibility` calculated by that exact rule, while keeping `requestedVisibility` as the submission snapshot. The UI shows the approval value only when it differs, and list responses remain unchanged.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, PostgreSQL, OpenAPI, React 19, TypeScript, i18next, Vitest, Playwright.

---

### Task 1: Review detail query and API contract

**Files:**
- Modify: `server-python/tests/test_review_detail.py`
- Modify: `server-python/tests/test_review_openapi_contract.py`
- Modify: `server-python/app/review/query.py`
- Modify: `server-python/app/api/reviews.py`

- [ ] **Step 1: Write failing query and contract tests**

Add `"requested_visibility": "NAMESPACE_ONLY"` to the active fake review row and assert:

```python
assert response["requestedVisibility"] == "NAMESPACE_ONLY"
```

Keep the archived fake row without that field and assert:

```python
assert response["requestedVisibility"] is None
```

Add the OpenAPI assertion:

```python
assert properties["requestedVisibility"]["anyOf"][0]["type"] == "string"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd server-python
uv run pytest tests/test_review_detail.py tests/test_review_openapi_contract.py -q
```

Expected: failures because the detail-only visibility fields are absent from the response and schema.

- [ ] **Step 3: Implement the minimal contract**

Add `_detail_task_response` on top of the unchanged list mapper. It must expose:

```python
"requestedVisibility": row.get("requested_visibility"),
"approvalVisibility": approval_visibility,
```

In `_read_review_task_row`, select the requested visibility, current visibility, and whether an `UPDATE_SKILL_VISIBILITY` audit entry exists after submission. Use the current value only when that audit condition is true; otherwise use the requested value.

```sql
sv.requested_visibility,
s.visibility AS current_visibility,
```

Add these optional fields to `ReviewTaskResponse`:

```python
requestedVisibility: str | None = None
approvalVisibility: str | None = None
```

- [ ] **Step 4: Run focused backend tests and verify GREEN**

Run the same pytest command and expect all selected tests to pass.

### Task 2: Real PostgreSQL snapshot verification

**Files:**
- Create: `server-python/tests/test_review_requested_visibility_postgres.py`

- [ ] **Step 1: Write the PostgreSQL integration test**

Create unique user, namespace, skill, version, membership, and review rows. Store `skill.visibility = 'PUBLIC'` and `skill_version.requested_visibility = 'NAMESPACE_ONLY'`, then call:

```python
detail = await read_review_detail(
    engine,
    review_task_id=review_task_id,
    user_id=namespace_owner_id,
)
assert detail["requestedVisibility"] == "NAMESPACE_ONLY"
```

The test must use `SKILLHUB_TEST_DATABASE_URL`, skip only when it is absent, and delete its unique fixture rows in `finally`.

- [ ] **Step 2: Run against the real PostgreSQL container and verify behavior**

Run:

```powershell
$env:SKILLHUB_TEST_DATABASE_URL = 'postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub'
cd server-python
uv run pytest tests/test_review_requested_visibility_postgres.py -q
```

Expected: PASS while proving current and requested visibility differ.

### Task 3: Generated review types and localized UI

**Files:**
- Modify: `web/src/api/generated/reviews-openapi.json` (generated)
- Modify: `web/src/api/generated/reviews-schema.d.ts` (generated)
- Modify: `web/src/api/types.ts`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/pages/dashboard/review-detail.test.tsx`
- Modify: `web/src/pages/dashboard/review-detail.tsx`

- [ ] **Step 1: Write failing UI tests**

Set `requestedVisibility: 'NAMESPACE_ONLY'` on the namespace review fixture and assert the rendered markup contains the requested visibility label and namespace-only value. Add another fixture with no requested value and assert the neutral fallback appears.

```typescript
expect(html).toContain('review.requestedVisibility')
expect(html).toContain('publish.visibilityOptions.namespaceOnly')
expect(html).toContain('review.visibilityNotRecorded')
```

- [ ] **Step 2: Run the UI test and verify RED**

Run:

```powershell
cd web
pnpm run test -- src/pages/dashboard/review-detail.test.tsx
```

Expected: failures because the review metadata grid does not render requested visibility.

- [ ] **Step 3: Regenerate the review OpenAPI artifacts**

Run:

```powershell
cd web
pnpm run generate-api:reviews
```

Do not edit either generated artifact manually. Confirm `ReviewTaskResponse` contains `requestedVisibility?: string | null` and keep the `ReviewTask` wrapper type generated-first.

- [ ] **Step 4: Add translations and render the badge**

Add these review keys in all three locale files:

```json
"requestedVisibility": "Requested visibility",
"visibilityNotRecorded": "Not recorded"
```

Use Traditional and Simplified Chinese equivalents in their locale files. In the metadata grid, map only known values:

```typescript
const requestedVisibilityLabel = review.requestedVisibility === 'PUBLIC'
  ? t('publish.visibilityOptions.public')
  : review.requestedVisibility === 'NAMESPACE_ONLY'
    ? review.namespace === 'global'
      ? t('publish.visibilityOptions.loggedInUsersOnly')
      : t('publish.visibilityOptions.namespaceOnly')
    : t('review.visibilityNotRecorded')
```

Render the value beneath `t('review.requestedVisibility')` without adding an edit control.

- [ ] **Step 5: Run focused frontend tests and verify GREEN**

Run the same Vitest command and expect all review detail tests to pass.

### Task 4: End-to-end verification and review

**Files:**
- Create: `web/e2e/review-requested-visibility.spec.ts`

- [ ] **Step 1: Add authenticated desktop and mobile E2E coverage**

Use the existing session fixture and a real review task whose current and requested visibility differ. For `1280x720` and `390x844`, open the namespace review detail route and assert the requested visibility label and `Namespace Only` value are visible while approve/reject controls remain available.

- [ ] **Step 2: Run focused and complete verification**

Run:

```powershell
cd server-python
uv run pytest tests/test_review_detail.py tests/test_review_openapi_contract.py tests/test_review_requested_visibility_postgres.py -q
uv run pytest tests -q
cd ..\web
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm exec playwright test e2e/review-requested-visibility.spec.ts --project=chromium
pnpm run build
cd ..
git diff --check
```

Expected: all commands pass. Existing production-build warnings may remain, but no new errors or warnings may be introduced.

- [ ] **Step 3: Perform a final code review**

Review the diff for these failure modes:

- current `skill.visibility` accidentally shown instead of requested visibility;
- namespace owner authorization changed;
- archived or null data causes a crash;
- generated OpenAPI artifacts were edited manually or left stale;
- mobile metadata grid overflows;
- visibility becomes editable from the review page.

Fix any finding and rerun the affected focused and complete verification commands before reporting completion.
