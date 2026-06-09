# Skill Confirm Publish API Migration

## Summary

Move the portal confirm-publish lifecycle route to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`
- `POST /api/web/skills/{namespace}/{slug}/confirm-publish`

This route publishes an already uploaded or draft PRIVATE skill version directly without review.
This milestone does not move rerelease, submit-review, admin hide/unhide, yank, or broader
governance routes.

## Java Reference

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillReviewSubmitService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/Skill.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/SkillVersion.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/ConfirmPublishRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLifecycleMutationResponse.java`

## Route Ownership

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/confirm-publish` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/confirm-publish` | java | python |

Still Java-owned:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/web/skills/{namespace}/{slug}/submit-review`
- admin hide/unhide/yank routes

## Java Parity Checklist

| Concern | Status | Notes |
| --- | --- | --- |
| API contract | covered | Java accepts JSON body `{ "version": "..." }` and returns `ok("response.success.updated", SkillLifecycleMutationResponse)` with `action = "CONFIRM_PUBLISH"` and `status = "PUBLISHED"`. |
| Authorization/session | covered for local bridge | Route requires `X-Mock-User-Id`. Java allows skill owner or namespace `OWNER`/`ADMIN`. |
| Database transaction atomicity | covered | Skill lookup, version lookup, lifecycle checks, version publish update, skill latest/update actor, and audit insert must happen in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Python must write `CONFIRM_PUBLISH`, `target_type = "SKILL_VERSION"`, target version id, actor user id, request id, client IP, user agent, and detail JSON `{"version":"..."}`. |
| Storage and side effects | not applicable | Confirm publish does not write/delete package storage. |
| Vite proxy boundary | covered | Only confirm-publish POST routes move to Python. Rerelease and submit-review remain Java-owned and must be checked. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite responses plus DB/audit state and adjacent route boundaries. |

## Implementation Plan

1. Add failing Python service tests for:
   - owner or namespace manager can confirm a PRIVATE `UPLOADED` version
   - `DRAFT` is accepted
   - non-private skill is rejected
   - non-`UPLOADED`/`DRAFT` version is rejected
   - non-owner/non-manager is rejected before mutation
2. Add failing route tests for v1/web aliases, JSON body parsing, and `X-Mock-User-Id`.
3. Add failing Vite proxy tests proving confirm-publish POST routes go to Python and adjacent
   rerelease/submit-review routes remain Java-owned.
4. Implement Python lifecycle workflow and FastAPI routes.
5. Add Windows live gate `verify-skill-confirm-publish-smoke`.
6. Update route registry, sequence plan, and result document.

## Verification

- `cd server-python; uv run pytest tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-confirm-publish-smoke`
- `git diff --name-only -- server` must be empty.
