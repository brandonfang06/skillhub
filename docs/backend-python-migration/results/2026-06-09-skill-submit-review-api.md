# Skill Submit Review API Migration Result

## Summary

Moved portal submit-review route ownership to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/web/skills/{namespace}/{slug}/submit-review`

Rerelease, admin hide/unhide, yank, and broader post-publish lifecycle/governance actions remain
Java-owned.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/submit-review` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/submit-review` | java | python |

## Java Reference Files

- `SkillLifecycleController.java`
- `SkillLifecycleAppService.java`
- `SkillReviewSubmitService.java`
- `ReviewTask.java`
- `SubmitReviewRequest.java`
- `SkillLifecycleMutationResponse.java`

## Behavior Implemented

- Requires local `X-Mock-User-Id`.
- Accepts JSON body `{ "version": "...", "targetVisibility": "PUBLIC|NAMESPACE_ONLY" }`.
- Allows skill owner or namespace `OWNER`/`ADMIN`.
- Allows target version statuses `UPLOADED` and `DRAFT`.
- Rejects duplicate pending review tasks for the version.
- Updates `skill_version.status` to `PENDING_REVIEW`.
- Persists `skill_version.requested_visibility` from `targetVisibility`.
- Creates a pending `review_task` with `version = 1`, `submitted_by`, and `submitted_at`.
- Writes `SUBMIT_REVIEW` audit with `target_type = SKILL_VERSION`.
- Returns Java-compatible SkillHub envelope and lifecycle mutation response:
  `{ skillId, versionId, action: "SUBMIT_REVIEW", status: "PENDING_REVIEW" }`.

## Java Parity Checklist Outcome

| Concern | Outcome |
| --- | --- |
| API contract | Covered by route tests and Windows Java/Python/Vite comparison. |
| Authorization/session | Covered for local mock-user bridge, owner, namespace manager, and missing-auth cases. |
| Database transaction atomicity | Covered: version update, review task insert, and audit insert run in one SQLAlchemy transaction. |
| Audit fields | Covered: actor, target type/id, request id, client IP, user agent, and detail JSON are written. |
| Storage side effects | Not applicable. |
| Vite proxy boundary | Covered: submit-review POST routes now route to Python; rerelease remains Java-owned and confirm-publish remains Python-owned. |
| Live verification | Passed on Windows. |

## Issues Found During Verification

- Ordinary PowerShell could run Python and Vite checks, but Docker API access was denied while
  starting the live gate. The same gate passed from the approved elevated execution path.
- The live gate stop phase printed Windows process-stop warnings for stale/elevated PIDs, but a
  follow-up `status` showed Java, Python, and Vite as stopped. Docker compose services were removed
  during the successful gate run.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
  - `38 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `23 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-submit-review-smoke`
  - Python/Vite prechecks passed.
  - Java/Python/Vite contract checks passed:
    - `responsesMatch: true`
    - `dbState: true`
    - `audit: true`
    - `rereleaseBoundaryJavaOwned: true`
    - `confirmPublishBoundaryStillPythonOwned: true`
    - `unauthenticatedSubmitRejected: true`
  - Playwright smoke passed: `6 passed`.
- Post-gate status:
  - Java backend stopped.
  - Python backend stopped.
  - Vite frontend stopped.

## Risks And Follow-Up

- OAuth/session/API-token semantics remain deferred with the broader auth migration.
- Rerelease, admin hide/unhide, and yank remain Java-owned and are the remaining Group E lifecycle
  candidates.
