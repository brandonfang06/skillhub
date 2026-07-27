# Rejected Republish And Skill Visibility Design

**Date:** 2026-07-27

## Goal

Deliver two related lifecycle improvements:

1. Reject reuse of a skill version that already has a `REJECTED` review result
   with a stable client-visible conflict instead of reaching a database foreign
   key failure.
2. Let a skill owner or namespace `OWNER`/`ADMIN` change the skill-level
   visibility after the initial publish from the Skill Detail lifecycle panel.

## Confirmed Product Rules

### Rejected version reuse

- A rejected version number is immutable history and cannot be reused.
- The user must correct the package based on the review result and increase the
  `version` in `SKILL.md` before publishing again.
- The rejected `skill_version` row and its completed `review_task` remain
  available as review history.
- Existing replacement behavior for editable, non-rejected versions remains
  unchanged.

### Visibility updates

- Visibility is a skill-level access scope independent from version status.
- Allowed values remain `PUBLIC`, `NAMESPACE_ONLY`, and `PRIVATE`.
- Changing visibility does not modify any `skill_version.status`,
  `latest_version_id`, or review task.
- An already `PUBLISHED` version remains published.
- An `UPLOADED` version remains unpublished. Changing from `PRIVATE` to
  `PUBLIC` or `NAMESPACE_ONLY` does not automatically submit it for review.
- Access changes take effect immediately, subject to the existing skill,
  namespace, hidden/archive, version-status, and authentication filters.

## Rejected Republish Backend Design

### Current failure

`find_replaceable_version()` currently returns the matching rejected version.
The replacement workflow then calls `cleanup_replaceable_version()`, which only
deletes a pending review task. A completed rejected review task still references
the version, so deleting the version violates the `review_task.skill_version_id`
foreign key and surfaces as HTTP 500.

### Normal request path

`PublishDryRunRepository.read_publish_conflicts()` already reads the existing
version status. `validate_publish_dry_run()` will treat `REJECTED` as a distinct
conflict and return the stable code:

```text
error.skill.publish.rejectedVersionReuse
```

The validate-only endpoint will continue returning its normal dry-run result
with `valid=false` and that code in `errors`. An actual publish request will map
the code to HTTP `409 Conflict` before replacement lookup, database mutation,
storage writes, scanner handoff, notification creation, or review creation.

### Write-boundary guard

The replacement layer will also reject a `ReplaceableVersion` whose status is
`REJECTED` before executing cleanup SQL. For an initially replaceable status,
the write transaction locks and re-reads the current `skill_version.status`
before cleanup. This protects direct workflow calls and the race where state
changes after dry-run or replacement lookup but before the publish transaction.

The route boundary will map the write-layer domain exception to the same HTTP
409 and stable code. The transaction will roll back without deleting review
history or package objects.

`PUBLISHED` version reuse remains rejected by its existing rule. Other current
replacement statuses retain their existing behavior.

## Visibility API Design

Add matching browser and versioned API route aliases:

```http
PATCH /api/web/skills/{namespace}/{slug}/visibility
PATCH /api/v1/skills/{namespace}/{slug}/visibility
Content-Type: application/json

{
  "visibility": "NAMESPACE_ONLY"
}
```

Successful response data:

```json
{
  "skillId": 123,
  "visibility": "NAMESPACE_ONLY",
  "changed": true
}
```

The response remains inside the repository's standard success envelope and
request-id behavior.

### Authorization

The workflow will reuse the lifecycle management policy:

- the skill owner is allowed;
- namespace `OWNER` and `ADMIN` are allowed;
- namespace `MEMBER`, unrelated users, and anonymous requests are denied.

The route authenticates the caller before entering the workflow. The workflow
reads the skill and namespace membership inside the transaction and enforces
authorization again at the mutation boundary.

### Transaction and audit

The workflow belongs in `server-python/app/lifecycle/skill.py` and reuses the
existing skill context, namespace-role, authorization, transaction, and audit
helpers. It locks the skill row while reading the previous visibility so
concurrent managers cannot produce stale audit history.

For a changed value it will:

1. update `skill.visibility`, `updated_by`, and `updated_at`;
2. write an `UPDATE_SKILL_VISIBILITY` audit record containing the previous and
   new visibility;
3. synchronize the existing denormalized search document for that skill;
4. commit all changes atomically.

Sending the current visibility is a successful idempotent no-op with
`changed=false`. It performs neither an `UPDATE` nor a duplicate audit write.

Invalid visibility values are rejected by the request contract. Missing skills
remain `404`; unauthorized callers remain `401` or `403`.

No schema migration, broad search-index rebuild, version-pointer recalculation,
storage operation, scanner operation, or notification fanout is required. The
single affected search document must be updated so access filters cannot retain
the previous visibility.

## Frontend Design

### Rejected publish message

The publish error utilities will recognize
`error.skill.publish.rejectedVersionReuse`. The publish page will display a
localized toast instead of the generic error:

- Traditional Chinese title: `無法重用已拒絕的版本`
- Traditional Chinese description:
  `請依照審核結果調整 skill，並更新 SKILL.md 中的 version 後重新發佈。`

Equivalent Simplified Chinese and English strings will be added. The raw
database error and generic HTTP 500 text will not be shown.

### Lifecycle visibility control

The existing Skill Detail lifecycle card will contain:

- a visibility select using the existing three translated visibility labels;
- concise helper text explaining immediate access changes and unchanged version
  status;
- a save button disabled when the value is unchanged or the mutation is
  pending;
- success and failure toasts.

The control is rendered only when `skill.canManageLifecycle` is true, which is
the existing read-model projection for a skill owner or namespace manager.
Other users continue seeing the read-only visibility badge.

The frontend API client will call the browser route with CSRF protection. A
TanStack Query mutation will invalidate the skill detail, My Skills, version
list, and general skill/search query families after success.

### Review action compatibility

The current review action is coupled to `PRIVATE` and submits the hard-coded
target `PUBLIC`. It will be aligned with the independent visibility setting:

- `UPLOADED + PRIVATE` keeps the private confirm-publish action;
- `UPLOADED + PUBLIC` shows submit-for-review with target `PUBLIC`;
- `UPLOADED + NAMESPACE_ONLY` shows submit-for-review with target
  `NAMESPACE_ONLY`;
- changing visibility never invokes either action automatically.

This prevents a user from changing visibility to a reviewable scope and then
losing the submit-review action.

## OpenAPI And Type Synchronization

The visibility request and response are part of the FastAPI OpenAPI contract.
After the route is implemented, regenerate
`web/src/api/generated/schema.d.ts` with the repository's API-generation
workflow. Generated files will not be edited manually.

## Testing Strategy

### Backend

- Dry-run test: own same-version `REJECTED` produces the stable conflict code.
- HTTP publish test: rejected reuse returns 409 and never invokes replacement
  lookup or the writer.
- Replacement test: a rejected replacement raises before any SQL statement.
- Race-path HTTP test: a write-layer rejected-version exception maps to the
  same 409 response.
- Visibility workflow tests:
  - skill owner succeeds;
  - namespace `OWNER` succeeds;
  - namespace `ADMIN` succeeds;
  - namespace `MEMBER` and unrelated users receive 403;
  - same-value request is a no-op;
  - changed value updates audit actor and old/new detail atomically;
  - failed audit or update rolls back the transaction.
- Visibility route tests:
  - unauthenticated request receives 401;
  - invalid visibility is rejected;
  - response envelope and request id are preserved.

### Frontend

- Error utility recognizes the stable rejected-version code.
- Publish page displays the dedicated localized toast.
- Visibility mutation sends the expected PATCH request with CSRF headers and
  invalidates all affected query families.
- Skill Detail tests cover manager-only rendering, disabled save state,
  successful update, and failure toast.
- Review-action tests cover `PRIVATE`, `PUBLIC`, and `NAMESPACE_ONLY` uploaded
  versions and verify the submitted target visibility.

### Browser verification

Authenticated Playwright coverage will verify:

- rejected same-version upload shows the dedicated message rather than a 500;
- a permitted manager changes visibility from the lifecycle card and sees the
  updated badge;
- a disallowed member has no edit control;
- desktop and mobile viewports keep the lifecycle control usable.

## Side Effects And Risk Controls

- Public broadening is immediate for an existing published version. The helper
  text makes this explicit before save.
- Restricting visibility immediately removes access for users who no longer
  match the new scope; owners and namespace managers retain protected read
  access through existing authorization.
- Private uploaded versions do not become public until the existing review
  workflow publishes them.
- Rejected review history is retained, so reviewer comments and audit evidence
  remain available.
- Auto-withdraw only reopens versions that are still `PENDING_REVIEW`, so a
  concurrent rejection cannot be overwritten before the locked replacement
  guard returns the stable 409.
- Approval preserves a manual visibility update recorded after review
  submission; otherwise it retains the existing requested-visibility behavior.
- Search indexing and reads select the current published fallback independently
  from the workflow latest pointer, so a private owner preview cannot hide the
  installable release.
- Visibility changes lock the namespace and skill rows and reject frozen or
  archived namespaces.
- Review optimistic updates treat a missing `RETURNING` row as a 409 conflict
  rather than an internal SQLAlchemy exception.

## Out Of Scope

- Reusing or renaming rejected version numbers.
- Editing rejected review records.
- Automatically submitting, approving, or publishing a version after a
  visibility change.
- Adding a separate Skill Settings page or a My Skills quick-action menu.
- Changing namespace visibility semantics or adding new visibility values.
