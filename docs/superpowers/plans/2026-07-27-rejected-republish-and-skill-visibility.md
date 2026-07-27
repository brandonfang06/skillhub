# Rejected Republish And Skill Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return a stable conflict for rejected version reuse and add a
permission-protected post-publish skill visibility control without changing
version state or core publish side effects.

**Architecture:** Detect rejected-version reuse in publish dry-run and guard it
again at the replacement write boundary. Add a focused lifecycle mutation and
FastAPI route for `skill.visibility`, then expose it through the existing Skill
Detail lifecycle card with TanStack Query and generated OpenAPI types.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy, pytest, React 19,
TypeScript, TanStack Query, Vitest, Playwright, i18next.

---

## File Map

### Rejected version conflict

- Modify: `server-python/app/publish/dry_run.py`
  - Define the stable conflict code and reject `REJECTED` in precheck.
- Modify: `server-python/app/publish/replacement.py`
  - Define the write-boundary domain exception and reject before cleanup SQL.
- Modify: `server-python/app/api/publish.py`
  - Map precheck and write-boundary rejected conflicts to HTTP 409.
- Modify: `server-python/tests/test_publish_dry_run.py`
- Modify: `server-python/tests/test_publish_replacement.py`
- Modify: `server-python/tests/test_publish_http_validate.py`

### Visibility mutation

- Modify: `server-python/app/lifecycle/skill.py`
  - Add the visibility input/result workflow, authorization, idempotency, and
    audit write.
- Modify: `server-python/app/api/lifecycle.py`
  - Add request schema, route helper, writer seam, and v1/web PATCH aliases.
- Create: `server-python/tests/test_skill_lifecycle_visibility.py`
  - Cover workflow permissions, no-op behavior, audit, rollback, and HTTP
    contract.
- Regenerate: `web/src/api/generated/schema.d.ts`

### Frontend

- Modify: `web/src/features/publish/publish-error-utils.ts`
- Modify: `web/src/features/publish/publish-error-utils.test.ts`
- Modify: `web/src/pages/dashboard/publish.tsx`
- Modify: `web/src/pages/dashboard/publish.test.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/shared/hooks/use-skill-queries.ts`
- Modify: `web/src/pages/skill-detail.tsx`
- Modify: `web/src/pages/skill-detail.test.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Create or modify: `web/e2e/skill-lifecycle-visibility.spec.ts`

## Task 1: Reject Reuse Of A Rejected Version

- [x] **Step 1: Write the dry-run regression test**

Add a test that passes:

```python
PublishConflictContext(own_version_status="REJECTED")
```

and asserts:

```python
assert not result.valid
assert result.errors == ["error.skill.publish.rejectedVersionReuse"]
```

- [x] **Step 2: Run the dry-run test and verify RED**

```powershell
cd server-python
uv run pytest tests/test_publish_dry_run.py -q
```

Expected: the new test fails because `REJECTED` is currently accepted.

- [x] **Step 3: Implement the dry-run conflict**

In `app/publish/dry_run.py`, define:

```python
REJECTED_VERSION_REUSE_ERROR = "error.skill.publish.rejectedVersionReuse"
```

Append it when `conflicts.own_version_status == "REJECTED"`.

- [x] **Step 4: Add the write-boundary failing test**

In `test_publish_replacement.py`, assert a rejected replacement raises
`RejectedVersionReuseError` and that `connection.statements == []`.

- [x] **Step 5: Run the replacement test and verify RED**

```powershell
uv run pytest tests/test_publish_replacement.py -q
```

Expected: import or assertion failure because the domain exception does not
exist.

- [x] **Step 6: Add the replacement guard**

In `app/publish/replacement.py`, add:

```python
class RejectedVersionReuseError(ValueError):
    pass
```

At the start of `cleanup_replaceable_version()`:

```python
if version.status == "REJECTED":
    raise RejectedVersionReuseError("error.skill.publish.rejectedVersionReuse")
```

This must execute before pointer updates, review deletion, file reads, security
audit updates, or version deletion. For an initially replaceable status, lock
and re-read the current version status inside the write transaction before any
cleanup so a post-lookup rejection cannot reuse the stale status.

- [x] **Step 7: Add HTTP conflict tests**

Cover both boundaries in `test_publish_http_validate.py`:

1. a dry-run result containing the stable code returns 409 and never calls the
   replacement reader or writer;
2. a writer that raises `RejectedVersionReuseError` returns the same 409 and
   error detail.

- [x] **Step 8: Run HTTP tests and verify RED**

```powershell
uv run pytest tests/test_publish_http_validate.py -q
```

- [x] **Step 9: Map both conflicts to HTTP 409**

In `app/api/publish.py`:

- choose status 409 when dry-run errors contain
  `REJECTED_VERSION_REUSE_ERROR`;
- catch `RejectedVersionReuseError` around the writer boundary and raise
  `HTTPException(status_code=409, detail=REJECTED_VERSION_REUSE_ERROR)`.

- [x] **Step 10: Verify Task 1 GREEN**

```powershell
uv run pytest tests/test_publish_dry_run.py tests/test_publish_replacement.py tests/test_publish_http_validate.py -q
```

## Task 2: Add The Visibility Workflow And API

- [x] **Step 1: Write visibility workflow tests**

Create `test_skill_lifecycle_visibility.py` with fake transaction results that
exercise:

- owner authorization;
- namespace `OWNER` and `ADMIN` authorization;
- `MEMBER` and unrelated user rejection;
- changed value update plus `UPDATE_SKILL_VISIBILITY` audit detail;
- same-value response with `changed=False` and no update/audit SQL;
- transaction exception propagation to prove update and audit share one unit of
  work.

Expected result shape:

```python
{
    "skillId": 101,
    "visibility": "NAMESPACE_ONLY",
    "changed": True,
}
```

- [x] **Step 2: Run workflow tests and verify RED**

```powershell
uv run pytest tests/test_skill_lifecycle_visibility.py -q
```

Expected: import failure for the missing input/workflow.

- [x] **Step 3: Implement the workflow**

Add to `app/lifecycle/skill.py`:

```python
SKILL_VISIBILITIES = {"PUBLIC", "NAMESPACE_ONLY", "PRIVATE"}

@dataclass(frozen=True)
class SkillVisibilityUpdateInput:
    namespace: str
    slug: str
    visibility: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None
```

`update_skill_visibility()` must reuse `_read_skill_context()`,
`_read_namespace_role()`, `_assert_can_manage()`, `transaction_connection()`,
`_write_audit()`, and the existing single-document search upsert. The changed
path updates only:

```sql
visibility = :visibility,
updated_by = :updated_by,
updated_at = :updated_at
```

Audit detail JSON must contain `previousVisibility` and `visibility`.
The same transaction must synchronize the affected
`skill_search_document.visibility`; no broad rebuild is allowed.

- [x] **Step 4: Write route tests**

Cover:

- v1 and web PATCH aliases;
- request-id envelope;
- authenticated writer input;
- missing user returns 401;
- invalid visibility returns 422;
- workflow 403 maps to HTTP 403.

- [x] **Step 5: Run route tests and verify RED**

```powershell
uv run pytest tests/test_skill_lifecycle_visibility.py -q
```

- [x] **Step 6: Implement the routes**

In `app/api/lifecycle.py`, define a request model using:

```python
visibility: Literal["PUBLIC", "NAMESPACE_ONLY", "PRIVATE"]
```

Add a route helper and:

```python
@router.patch("/api/v1/skills/{namespace}/{slug}/visibility")
@router.patch("/api/web/skills/{namespace}/{slug}/visibility")
```

Use the `skill_visibility_writer` app-state seam in route tests and map
`SkillLifecycleError` without adding route-level SQL.

- [x] **Step 7: Verify Task 2 GREEN**

```powershell
uv run pytest tests/test_skill_lifecycle_visibility.py tests/test_skill_lifecycle_archive.py -q
```

## Task 3: Verify The Runtime OpenAPI Contract

- [x] **Step 1: Start the backend for contract verification**

```powershell
cd server-python
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

- [x] **Step 2: Attempt regeneration and inspect the resulting scope**

```powershell
cd ..\web
corepack pnpm run generate-api
```

The FastAPI `/openapi.json` contract contained both visibility PATCH aliases
and the request enum. The tracked frontend schema and generation scripts still
target the retired Java `/v3/api-docs` baseline, so regenerating from FastAPI
produced more than 10,000 lines of unrelated contract drift. Treat that
baseline migration as separate maintenance work rather than widening this
feature.

- [x] **Step 3: Stop the temporary backend and remove unrelated drift**

```powershell
git diff -- web/src/api/generated/schema.d.ts
```

The temporary backend stopped cleanly. The generated file was restored from
the feature branch baseline and has no diff; frontend lifecycle calls continue
to follow the existing typed client pattern.

## Task 4: Add The Rejected-Version Frontend Message

- [x] **Step 1: Write error utility and publish-page tests**

Add a failing unit test:

```typescript
expect(
  isRejectedVersionReuseMessage('error.skill.publish.rejectedVersionReuse'),
).toBe(true)
```

Add a publish-page error-path test that rejects the mutation with an `ApiError`
carrying the stable code and asserts the dedicated toast translation keys are
used.

- [x] **Step 2: Run the tests and verify RED**

```powershell
cd web
corepack pnpm exec vitest run src/features/publish/publish-error-utils.test.ts src/pages/dashboard/publish.test.ts
```

- [x] **Step 3: Implement error mapping and translations**

Add `isRejectedVersionReuseMessage()` and handle it before generic version
errors in `publish.tsx`.

Add these keys under `publish` in all three locales:

```json
{
  "rejectedVersionReuseTitle": "Unable to reuse rejected version",
  "rejectedVersionReuseDescription": "Update the skill based on the review result, increase the version in SKILL.md, rebuild the package, and publish again."
}
```

Use the confirmed localized Chinese wording in `zh.json` and `zh-TW.json`.

- [x] **Step 4: Verify Task 4 GREEN**

Run the same two Vitest files and require all tests to pass.

## Task 5: Add The Lifecycle Visibility Control

- [x] **Step 1: Write API client and hook tests**

Verify the client:

- sends PATCH to the web visibility endpoint;
- uses JSON and CSRF headers;
- returns `{skillId, visibility, changed}`.

Verify the mutation invalidates:

- `['skills', 'my']`;
- the current skill detail;
- the current version list;
- the general `['skills']` family.

- [x] **Step 2: Write Skill Detail behavior tests**

Add failing tests for:

- control rendered only when `canManageLifecycle` is true;
- current visibility is selected;
- save disabled when unchanged;
- success and failure toast behavior;
- `UPLOADED + PRIVATE` keeps confirm publish;
- `UPLOADED + PUBLIC` submits review with `PUBLIC`;
- `UPLOADED + NAMESPACE_ONLY` submits review with `NAMESPACE_ONLY`;
- visibility mutation does not invoke submit-review or confirm-publish.

- [x] **Step 3: Run tests and verify RED**

```powershell
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx src/shared/hooks/use-skill-queries.test.ts
```

- [x] **Step 4: Implement client and hook**

Add `skillLifecycleApi.updateVisibility()` in `web/src/api/client.ts` and
`useUpdateSkillVisibility()` in `use-skill-queries.ts`.

- [x] **Step 5: Implement the Lifecycle card control**

Use the existing `Select` and `Button` components. Keep local draft visibility
separate from `skill.visibility`; synchronize it when refreshed server data
changes. Save only on explicit click.

Update review-action conditions so the current non-private visibility is used
as `targetVisibility`.

- [x] **Step 6: Add localized lifecycle labels**

Add title, helper, save, saving, success, and failure strings to all three
locales. The helper must state that access changes immediately while version
status and review state do not change automatically.

- [x] **Step 7: Verify Task 5 GREEN**

```powershell
corepack pnpm exec vitest run src/pages/skill-detail.test.tsx src/shared/hooks/use-skill-queries.test.ts
corepack pnpm run typecheck
corepack pnpm run lint
```

## Task 6: Integration And Side-Effect Verification

- [x] **Step 1: Add authenticated Playwright coverage**

Use the existing authenticated E2E fixtures and API setup patterns. Verify the
rejected publish message and visibility lifecycle control on desktop and mobile
viewports. Confirm a plain namespace member has no visibility edit control.
Also cover approval after a manual visibility change, published-version search
fallback while a newer private preview exists, and archived-namespace rejection.

- [x] **Step 2: Run focused E2E**

```powershell
cd web
corepack pnpm exec playwright test e2e/skill-lifecycle-visibility.spec.ts
```

- [x] **Step 3: Run complete backend tests**

```powershell
cd ..\server-python
uv run pytest tests -q
```

- [x] **Step 4: Run complete frontend gates**

```powershell
cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build
```

- [x] **Step 5: Run repository checks**

```powershell
cd ..
git diff --check
git status --short
```

Expected scope:

- no schema migration;
- no scanner, storage, download, search ranking, or deployment change;
- only the spec/plan and files listed in this plan;
- rejected review history remains preserved;
- visibility changes do not mutate version status or review tasks.

### Deep Review Hardening

Production-like PostgreSQL and authenticated browser scenarios exposed issues
that isolated unit tests had not detected:

- pending review approval reapplied stale `requested_visibility`, so approval
  could reopen a skill that was manually changed to `PRIVATE`;
- search indexing and reads required `latest_version_id` itself to be
  `PUBLISHED`, hiding an older valid published version when a private owner
  preview became latest;
- visibility writes did not reject frozen or archived namespaces or lock the
  namespace row against a concurrent state transition;
- auto-withdraw could overwrite a concurrently rejected version back to
  `UPLOADED`;
- review optimistic writes used `scalar_one()`, so a legitimate no-row race
  raised an internal exception instead of the intended 409 conflict.

The fixes preserve a visibility audit made after review submission, resolve a
published fallback independently from the workflow latest pointer, lock both
namespace and skill rows for visibility changes, condition auto-withdraw on
`PENDING_REVIEW`, and map no-row review writes to
`review.concurrent_update`.

### Final Verification Results

- `uv run pytest tests -q`: `957 passed`.
- `corepack pnpm exec vitest run --maxWorkers=4`: `194` files and `697`
  tests passed. The default high-concurrency run first produced four unrelated
  5-second dynamic-import timeouts; those four files passed `20/20` in an
  immediate focused rerun before the stable full rerun.
- `corepack pnpm run typecheck`: passed.
- `corepack pnpm run lint`: passed.
- `corepack pnpm run build`: passed with the existing runtime-config and chunk-size warnings.
- Authenticated Chromium E2E: `5 passed`, covering the rejected-version `409`,
  owner/member behavior at `1440x900` and `390x844`, approval after a manual
  visibility restriction, published fallback search, and archived namespace
  rejection.
- The E2E also verified that changing to `PRIVATE` immediately removes a plain
  namespace member's detail and search access, while changing to
  `NAMESPACE_ONLY` restores read access without exposing the edit control.
- `git diff --check`: passed.
