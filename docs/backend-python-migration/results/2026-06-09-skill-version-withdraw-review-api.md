# Skill Version Withdraw Review API Migration Result

## Summary

Moved portal skill-version withdraw-review route ownership to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review`

At the time this milestone landed, rerelease, submit-review, confirm-publish, admin hide/unhide,
and yank routes remained Java-owned. Later lifecycle milestones moved submit-review and
confirm-publish to Python.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | java | python |

## Java Reference Files

- `SkillLifecycleController.java`
- `SkillLifecycleAppService.java`
- `ReviewService.java`
- `SkillGovernanceService.java`
- `SkillVersion.java`
- `ReviewTask.java`

## Behavior Implemented

- Requires local `X-Mock-User-Id`.
- Finds skill by namespace/slug and version by version string.
- Requires an active namespace.
- Requires a pending review task for the target version.
- Allows only the original review submitter to withdraw.
- Requires the target version to be `PENDING_REVIEW`.
- Deletes the pending review task.
- Updates `skill_version.status` to `UPLOADED`.
- Updates `skill.updated_by` and `skill.updated_at`.
- Writes `REVIEW_WITHDRAW` audit with `target_type = SKILL_VERSION`.
- Returns Java-compatible SkillHub envelope and lifecycle mutation response:
  `{ skillId, versionId, action: "WITHDRAW_REVIEW", status: "UPLOADED" }`.

## Java Parity Checklist Outcome

| Concern | Outcome |
| --- | --- |
| API contract | Covered by route tests and Windows Java/Python/Vite comparison. |
| Authorization/session | Covered for local mock-user bridge and submitter-only rule. |
| Database transaction atomicity | Covered: task delete, version update, skill update, and audit insert run in one SQLAlchemy transaction. |
| Audit fields | Covered: actor, target type/id, request id, client IP, user agent, and detail JSON are written. |
| Storage side effects | Not applicable. |
| Vite proxy boundary | Covered: withdraw-review POST routes route to Python; current adjacent checks keep rerelease Java-owned and confirm submit-review/confirm-publish remain Python-owned. |
| Live verification | Passed on Windows. |

## Issues Found During Verification

1. Python initially attempted to update `skill_version.updated_at`, but the Java/Flyway schema has
   no such column. Fixed by removing that write and adding a test assertion that the update SQL does
   not reference `updated_at`.
2. The first live comparator incorrectly compared exact `versionId` values across different Java,
   Python, and Vite fixtures. Fixed by comparing stable presence fields, matching the existing
   delete-version gate strategy.
3. Post-review correction: Python initially mapped every non-`ACTIVE` namespace on
   withdraw-review to `error.namespace.archived` with HTTP 403. Java `ReviewService` distinguishes
   `FROZEN` and `ARCHIVED` and raises bad-request errors. Fixed by mapping `FROZEN` to
   `error.namespace.frozen` and `ARCHIVED` to `error.namespace.archived`, both with HTTP 400.
4. Post-review correction: the withdraw-review live gate still expected submit-review and
   confirm-publish to be Java-owned after those routes had moved to Python. Updated the gate to
   verify they remain Python-owned and reject unauthenticated valid requests with 401.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
  - `23 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `23 passed`
- Post-review fix verification:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_submit_review.py tests/test_hybrid_makefile.py -q`
  - `40 passed, 1 warning`
  - `cd web; npx.cmd vitest run vite.config.test.ts`
  - `23 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-version-withdraw-review-smoke`
  - Python/Vite prechecks passed.
  - Java/Python/Vite contract checks passed:
    - `responsesMatch: true`
    - `dbState: true`
    - `audit: true`
    - `rereleaseBoundaryJavaOwned: true`
    - `submitReviewBoundaryStillPythonOwned: true`
    - `confirmPublishBoundaryStillPythonOwned: true`
    - `unauthenticatedWithdrawRejected: true`
  - Playwright smoke passed: `6 passed`.
- Post-gate status:
  - Java backend stopped.
  - Python backend stopped.
  - Vite frontend stopped.
  - Docker compose services stopped.

## Risks And Follow-Up

- OAuth/session/API-token semantics remain deferred with the broader auth migration.
- Rerelease, admin hide/unhide, and yank remain Java-owned and are candidates for later
  lifecycle/governance milestones.
