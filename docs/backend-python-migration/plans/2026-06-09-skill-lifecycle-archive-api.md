# Skill Lifecycle Archive API Plan

## Summary

Move the portal skill archive/unarchive routes to Python:

- `POST /api/v1/skills/{namespace}/{slug}/archive`
- `POST /api/web/skills/{namespace}/{slug}/archive`
- `POST /api/v1/skills/{namespace}/{slug}/unarchive`
- `POST /api/web/skills/{namespace}/{slug}/unarchive`

This milestone intentionally does not move version deletion, withdraw-review, rerelease,
submit-review, confirm-publish, admin hide/unhide, or yank routes.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/archive` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/archive` | java | python |
| POST | `/api/v1/skills/{namespace}/{slug}/unarchive` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/unarchive` | java | python |

All other lifecycle/governance routes remain Java-owned.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillLifecycleMutationResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminSkillActionRequest.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Return Java envelope with `skillId`, `versionId`, `action`, and `status`. |
| Authorization/session | covered for local bridge | Require `X-Mock-User-Id`; allow skill owner or namespace `OWNER`/`ADMIN`. OAuth/session remains Java-owned. |
| Database transaction atomicity | covered | Skill status update and audit insert happen in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Write `ARCHIVE_SKILL`/`UNARCHIVE_SKILL`, actor, target, IP, user-agent, and reason JSON for archive. |
| Storage and side effects | deferred | Java publishes status-change events; Python will record DB/audit parity here and defer async event/search notification effects to a later lifecycle event milestone. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite archive/unarchive contracts and DB/audit state. |

## Implementation Steps

1. Add failing tests for archive/unarchive workflow and API route envelopes.
2. Add failing Vite proxy tests proving only archive/unarchive POST routes move to Python.
3. Implement `server-python/app/lifecycle/skill.py` archive/unarchive workflow.
4. Add FastAPI routes under a new lifecycle router and include it in `create_app`.
5. Update Vite method-aware proxy rules.
6. Add a Windows live gate in `scripts/dev-hybrid.ps1`.
7. Update route registry, migration sequence plan, and result document.

## Verification

- `cd server-python; uv run pytest tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
- `cd web; npx vitest run vite.config.test.ts`
- `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-lifecycle-archive-smoke`
- `git diff --name-only -- server` must return no paths.
