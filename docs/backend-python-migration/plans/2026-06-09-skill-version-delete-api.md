# Skill Version Delete API Plan

## Summary

Move version deletion routes to Python and resolve the observed Vite proxy boundary issue for this
path by making delete-version a real Python-owned mutation:

- `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `DELETE /api/web/skills/{namespace}/{slug}/versions/{version}`

This milestone does not move withdraw-review, rerelease, submit-review, confirm-publish, admin
hide/unhide, or yank routes.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| DELETE | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | java / proxy-boundary ambiguous | python |
| DELETE | `/api/web/skills/{namespace}/{slug}/versions/{version}` | java | python |

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLifecycleMutationResponse.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Return Java envelope with `skillId`, `versionId`, `action = DELETE_VERSION`, and `status = version string`. |
| Authorization/session | covered for local bridge | Require `X-Mock-User-Id`; allow skill owner or namespace `OWNER`/`ADMIN`. OAuth/session remains Java-owned. |
| Database transaction atomicity | covered | Version eligibility, latest recalculation, file metadata delete, security audit soft-delete, version delete, and audit insert happen in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Write `DELETE_SKILL_VERSION` with `{"version": "<version>"}` detail. |
| Storage and side effects | covered for local storage | Collect file object keys plus bundle key in the transaction; after commit delete local storage objects or record compensation. S3/MinIO abstraction remains a later storage refactor. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite DB/audit behavior and proves rerelease/submit-review remain Java-owned. |

## Implementation Steps

1. Add failing tests for delete-version workflow:
   - allowed statuses: `DRAFT`, `REJECTED`, `SCAN_FAILED`, `UPLOADED`
   - unsupported status rejected
   - last version rejected
   - files/security audits/version deleted
   - latest published version recalculated when needed
   - audit and storage keys produced
2. Add failing route tests for v1/web delete aliases and `X-Mock-User-Id`.
3. Add failing Vite proxy tests for DELETE ownership and non-owned lifecycle route boundaries.
4. Implement Python delete-version workflow and route.
5. Update Vite method-aware proxy ownership.
6. Add Windows live gate.
7. Update route registry, sequence plan, and result document.

## Verification

- `cd server-python; uv run pytest tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
- `cd web; npx vitest run vite.config.test.ts`
- `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-version-delete-smoke`
- `git diff --name-only -- server` must return no paths.
