# Admin Version Yank API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move platform-admin skill version yank moderation action from Java to FastAPI.

**Architecture:** Python will extend the existing admin-governance route module. The route resolves
the local mock user, requires `SKILL_ADMIN` or `SUPER_ADMIN`, yanks only `PUBLISHED` versions,
recalculates `skill.latest_version_id` when needed, and writes Java-compatible audit rows. Vite will
route only the admin version yank POST route to Python.

**Tech Stack:** FastAPI, SQLAlchemy async `text`, existing auth mock-user bridge, Vite method-aware
proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `POST /api/v1/admin/skills/versions/{versionId}/yank`

Already Python-owned:

- `POST /api/v1/admin/skills/{skillId}/hide`
- `POST /api/v1/admin/skills/{skillId}/unhide`

Remain Java-owned:

- Other admin skill, report, label, search, user-management, and profile-review APIs.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminSkillController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminSkillActionRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminSkillMutationResponse.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | Yank accepts optional `reason` body and returns update-success envelope with `AdminSkillMutationResponse`. |
| Authorization/session | planned | Requires local mock user with `SKILL_ADMIN` or `SUPER_ADMIN`; missing user and unrelated roles are rejected. |
| Database transaction atomicity | planned | Version mutation, latest-version recalculation, skill update when needed, and audit insert happen in one DB transaction. |
| Version state parity | planned | Only `PUBLISHED` can be yanked. Target version becomes `YANKED`, gets `yanked_at`, `yanked_by`, `yank_reason`, and `download_ready=false`. |
| Latest pointer parity | planned | If yanked version is current latest, recalculate latest from remaining `PUBLISHED` versions ordered by `published_at`, `created_at`, then `id`. |
| Audit actor/timestamp fields | planned | Writes `YANK_SKILL_VERSION` on target type `SKILL_VERSION` with optional `{"reason":...}` detail. |
| Event parity | deferred | Java publishes `SkillVersionYankedEvent`. Python has no equivalent event bus yet; record this as a known broader migration follow-up. |
| Vite proxy boundary | planned | Only admin version yank POST moves to Python; unrelated admin routes remain Java-owned/fallback. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite response, DB state, latest pointer, audit rows, role rejections, and unrelated admin fallback boundary. |

## TDD Steps

- [x] Add failing Python tests for yank workflow, latest-version recalculation, status validation, and route behavior.
- [x] Run the new tests and confirm they fail before implementation.
- [x] Implement minimal Python admin-governance workflow and FastAPI yank route.
- [x] Add failing Vite proxy tests for yank ownership while unrelated admin routes remain Java-owned.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for admin version yank.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [x] Commit and push to `dev`.

## Acceptance Criteria

- `SKILL_ADMIN` and `SUPER_ADMIN` can yank a `PUBLISHED` version.
- Non-published versions are rejected with Java-compatible `error.skill.version.notPublished`.
- Missing version is rejected with Java-compatible `error.skill.version.notFound`.
- Yank updates version status and yanked fields without touching storage.
- If yanked version is latest, `skill.latest_version_id` moves to the newest remaining published
  version or null when none remain, and `skill.updated_by` is set to the actor.
- If yanked version is not latest, `skill.latest_version_id` is not rewritten.
- Response action/status match Java: `YANK`, `versionId=<id>`, status `YANKED`.
- Vite routes admin version yank to Python.
- No files under `server/` are modified.
