# Skill Confirm Publish API Migration Result

## Summary

Moved portal confirm-publish route ownership to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`
- `POST /api/web/skills/{namespace}/{slug}/confirm-publish`

Rerelease, submit-review, admin hide/unhide, and yank remain Java-owned.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/confirm-publish` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/confirm-publish` | java | python |

## Java Reference Files

- `SkillLifecycleController.java`
- `SkillLifecycleAppService.java`
- `SkillReviewSubmitService.java`
- `Skill.java`
- `SkillVersion.java`
- `ConfirmPublishRequest.java`
- `SkillLifecycleMutationResponse.java`

## Behavior Implemented

- Requires local `X-Mock-User-Id`.
- Accepts JSON body `{ "version": "..." }`.
- Allows skill owner or namespace `OWNER`/`ADMIN`.
- Requires `skill.visibility = PRIVATE`.
- Allows target version statuses `UPLOADED` and `DRAFT`.
- Updates `skill_version.status` to `PUBLISHED` and sets `published_at`.
- Updates `skill.latest_version_id`, `skill.updated_by`, and `skill.updated_at`.
- Writes `CONFIRM_PUBLISH` audit with `target_type = SKILL_VERSION`.
- Returns Java-compatible SkillHub envelope and lifecycle mutation response:
  `{ skillId, versionId, action: "CONFIRM_PUBLISH", status: "PUBLISHED" }`.

## Java Parity Checklist Outcome

| Concern | Outcome |
| --- | --- |
| API contract | Covered by route tests and Windows Java/Python/Vite comparison. |
| Authorization/session | Covered for local mock-user bridge, owner, namespace manager, and missing-auth cases. |
| Database transaction atomicity | Covered: version publish update, skill latest/update actor, and audit insert run in one SQLAlchemy transaction. |
| Audit fields | Covered: actor, target type/id, request id, client IP, user agent, and detail JSON are written. |
| Storage side effects | Not applicable. |
| Vite proxy boundary | Covered: confirm-publish POST routes now route to Python; rerelease and submit-review still match Java fallback behavior. |
| Live verification | Passed on Windows. |

## Issues Found During Verification

- The first unauthenticated live-gate probe sent an empty POST, so FastAPI returned `422` body
  validation before reaching the auth check. The gate now sends a valid JSON body without
  `X-Mock-User-Id`, correctly verifying `401`.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
  - `30 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `23 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-confirm-publish-smoke`
  - Python/Vite prechecks passed.
  - Java/Python/Vite contract checks passed:
    - `responsesMatch: true`
    - `dbState: true`
    - `audit: true`
    - `rereleaseBoundaryJavaOwned: true`
    - `submitReviewBoundaryJavaOwned: true`
    - `unauthenticatedConfirmRejected: true`
  - Playwright smoke passed: `6 passed`.
- Post-gate status:
  - Java backend stopped.
  - Python backend stopped.
  - Vite frontend stopped.
  - Docker compose services stopped.

## Risks And Follow-Up

- OAuth/session/API-token semantics remain deferred with the broader auth migration.
- Rerelease, submit-review, admin hide/unhide, and yank remain Java-owned and are candidates for
  later lifecycle/governance milestones.
