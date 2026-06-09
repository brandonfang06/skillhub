# Skill Submit Review API Migration

## Summary

Move the portal skill lifecycle submit-review route to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/web/skills/{namespace}/{slug}/submit-review`

This route submits an uploaded or draft skill version for review with target visibility `PUBLIC`
or `NAMESPACE_ONLY`. This milestone does not move rerelease, admin hide/unhide, yank, or broader
governance routes.

## Java Reference

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillReviewSubmitService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewTask.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SubmitReviewRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLifecycleMutationResponse.java`

## Route Ownership

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/submit-review` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/submit-review` | java | python |

Still Java-owned:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`
- admin hide/unhide/yank routes

## Java Parity Checklist

| Concern | Status | Notes |
| --- | --- | --- |
| API contract | covered | Java accepts `{ "version": "...", "targetVisibility": "PUBLIC|NAMESPACE_ONLY" }` and returns `ok("response.success.updated", SkillLifecycleMutationResponse)` with `action = "SUBMIT_REVIEW"` and `status = "PENDING_REVIEW"`. |
| Authorization/session | covered for local bridge | Route requires `X-Mock-User-Id`. Java allows skill owner or namespace `OWNER`/`ADMIN`; this lifecycle route should not reuse broader review-list platform role rules. |
| Database transaction atomicity | covered | Version update, review task insert, and lifecycle audit insert must happen in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Java lifecycle route writes `SUBMIT_REVIEW`, `target_type = "SKILL_VERSION"`, target version id, actor user id, request id, client IP, user agent, and detail JSON `{"version":"...","targetVisibility":"..."}`. |
| Storage and side effects | not applicable | Submit review does not write/delete package storage. |
| Vite proxy boundary | covered | Only submit-review POST routes move to Python. Rerelease remains Java-owned and must be checked. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite responses plus DB/audit state and adjacent route boundaries. |

## Important Parity Note

This route is not the same contract as `POST /api/v1/reviews`.

- `/api/v1/reviews` returns a review task response and writes `REVIEW_SUBMIT` target
  `REVIEW_TASK`.
- `/api/v1/skills/{namespace}/{slug}/submit-review` returns `SkillLifecycleMutationResponse` and
  writes `SUBMIT_REVIEW` target `SKILL_VERSION`.

Python must keep these paths separate.

## Implementation Plan

1. Add failing Python service tests for:
   - owner or namespace manager can submit `UPLOADED`/`DRAFT` version
   - target visibility is persisted on `skill_version.requested_visibility`
   - review task row is created
   - non-`UPLOADED`/`DRAFT` version is rejected
   - non-owner/non-manager is rejected before mutation
2. Add failing route tests for v1/web aliases, JSON body parsing, and `X-Mock-User-Id`.
3. Add failing Vite proxy tests proving submit-review POST routes go to Python and rerelease remains Java-owned.
4. Implement Python lifecycle workflow and FastAPI routes.
5. Add Windows live gate `verify-skill-submit-review-smoke`.
6. Update route registry, sequence plan, and result document.

## Verification

- `cd server-python; uv run pytest tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-submit-review-smoke`
- `git diff --name-only -- server` must be empty.
