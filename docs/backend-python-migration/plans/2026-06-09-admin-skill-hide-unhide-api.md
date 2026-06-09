# Admin Skill Hide Unhide API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move platform-admin skill hide/unhide moderation actions from Java to FastAPI.

**Architecture:** Python will add a small admin-governance route module that resolves the local
mock user, enforces `SUPER_ADMIN`, updates the skill hidden overlay fields, and writes
Java-compatible audit rows. Vite will route only hide/unhide admin skill POST routes to Python;
admin yank remains Java-owned.

**Tech Stack:** FastAPI, SQLAlchemy async `text`, existing auth mock-user bridge, Vite
method-aware proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `POST /api/v1/admin/skills/{skillId}/hide`
- `POST /api/v1/admin/skills/{skillId}/unhide`

Remain Java-owned:

- `POST /api/v1/admin/skills/versions/{versionId}/yank`
- Other admin skill, report, label, search, user-management, and profile-review APIs.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminSkillController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminSkillActionRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminSkillMutationResponse.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | Hide accepts optional `reason`; unhide accepts no required body. Both return update-success envelope and `AdminSkillMutationResponse`. |
| Authorization/session | planned | Requires local mock user with `SUPER_ADMIN`; `SKILL_ADMIN` and other roles are rejected for hide/unhide. |
| Database transaction atomicity | planned | Each action updates skill overlay fields and writes audit in one DB transaction. |
| Audit actor/timestamp fields | planned | Hide writes `HIDE_SKILL` with optional `{"reason":...}` detail. Unhide writes `UNHIDE_SKILL` with null detail. |
| Storage and side effects | not applicable | No file/object storage mutation. |
| Vite proxy boundary | planned | Only hide/unhide POST routes move to Python. Yank remains Java-owned/fallback. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite response, DB hidden fields, audit rows, role rejections, and yank boundary. |

## TDD Steps

- [x] Add failing Python tests for hide/unhide workflow and route behavior.
- [x] Run the new test file and confirm it fails before implementation.
- [x] Implement minimal Python admin-governance workflow and FastAPI routes.
- [x] Add failing Vite proxy tests for hide/unhide ownership while yank remains Java-owned.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for admin hide/unhide.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [x] Commit and push to `dev`.

## Acceptance Criteria

- `SUPER_ADMIN` can hide a skill; DB `hidden=true`, `hidden_by`, `hidden_at`, `updated_by` are updated.
- `SUPER_ADMIN` can unhide a skill; DB `hidden=false`, `hidden_by=null`, `hidden_at=null`, `updated_by` is updated.
- `SKILL_ADMIN`, `USER_ADMIN`, missing user, and missing mock header cannot hide/unhide.
- Response action/status match Java: `HIDE`/`UNHIDE`, `versionId=null`, status is current skill container status.
- Vite routes hide/unhide to Python and keeps yank Java-owned.
- No files under `server/` are modified.
