# Skill Version Withdraw Review API Migration

## Summary

Move the portal skill-version withdraw-review lifecycle route to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review`

This milestone is intentionally limited to the namespace/slug/version withdraw-review entrypoint.
It does not move rerelease, submit-review, confirm-publish, admin hide/unhide, yank, or broader
governance routes.

## Java Reference

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/SkillVersion.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewTask.java`

## Route Ownership

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | java | python |

Still Java-owned:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/web/skills/{namespace}/{slug}/submit-review`
- `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`
- `POST /api/web/skills/{namespace}/{slug}/confirm-publish`
- admin hide/unhide/yank routes

## Java Parity Checklist

| Concern | Status | Notes |
| --- | --- | --- |
| API contract | covered | Java returns `ok("response.success.updated", SkillLifecycleMutationResponse)` with fields `skillId`, `versionId`, `action = "WITHDRAW_REVIEW"`, `status = "UPLOADED"`. |
| Authorization/session | covered for local bridge | Route requires `X-Mock-User-Id`. Java delegates to `ReviewService.withdrawReview(...)`, which allows only the pending review task submitter. |
| Database transaction atomicity | covered | Skill lookup, version lookup, pending review task delete, version status update, skill `updated_by`, and audit insert must happen inside one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Python must write `REVIEW_WITHDRAW`, `target_type = "SKILL_VERSION"`, target version id, actor user id, request id, client IP, user agent, and detail JSON `{"version":"..."}`. |
| Storage and side effects | not applicable | Withdraw-review does not write or delete storage objects. |
| Vite proxy boundary | covered | Only the withdraw-review POST routes move to Python. Rerelease, submit-review, and confirm-publish remain Java-owned and must be checked. |
| Live verification evidence | planned | Windows live gate compares Java/Python/Vite responses and DB/audit state, and checks adjacent Java-owned boundaries. |

## Implementation Plan

1. Add failing Python service tests for:
   - pending review task submitter can withdraw by skill coordinate/version
   - non-submitter is rejected before DB mutation
   - missing pending review task is rejected
   - non-`PENDING_REVIEW` version is rejected
2. Add failing route tests for v1/web aliases and `X-Mock-User-Id` requirement.
3. Add failing Vite proxy tests proving withdraw-review POST routes go to Python and adjacent routes remain Java-owned.
4. Implement Python lifecycle workflow and FastAPI routes.
5. Add Windows live gate `verify-skill-version-withdraw-review-smoke`.
6. Update route registry, sequence plan, and result document.

## Verification

- `cd server-python; uv run pytest tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-version-withdraw-review-smoke`
- `git diff --name-only -- server` must be empty.
