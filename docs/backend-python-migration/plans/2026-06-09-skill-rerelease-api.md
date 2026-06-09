# Skill Rerelease API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move portal skill version rerelease actions from Java to FastAPI while preserving Java
contract and lifecycle behavior.

**Architecture:** Python will add a lifecycle wrapper that reads a published source version,
rebuilds package entries from `skill_file` storage objects, rewrites `SKILL.md` frontmatter
`version`, delegates new version creation to the existing Python publish orchestration path, then
writes the Java-compatible `RERELEASE_SKILL_VERSION` lifecycle audit. Vite will route only the two
rerelease POST aliases to Python.

**Tech Stack:** FastAPI, SQLAlchemy async `text`, existing Python publish orchestration, local
storage bridge, Vite method-aware proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`

Remain Java-owned:

- Admin hide/unhide routes.
- Yank routes.
- Any route not explicitly listed above.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLifecycleAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillVersionRereleaseRequest.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | Request body has required `targetVersion` and boolean `confirmWarnings`; response is `response.success.updated` envelope with `RERELEASE_VERSION`. |
| Authorization/session | planned | Requires local mock user and uses owner or namespace `OWNER`/`ADMIN`, matching lifecycle management checks. |
| Database transaction atomicity | planned | Existing publish orchestration keeps DB writes, local storage writes, side effects, and storage failure cleanup inside the Python publish path. Rerelease adds lifecycle audit after the publish result in the same milestone flow. |
| Audit actor/timestamp fields | planned | Publish side effects keep existing publish audit behavior; lifecycle route additionally writes `RERELEASE_SKILL_VERSION` on the source version with `sourceVersion` and trimmed `targetVersion`. |
| Storage and side effects | planned | Source version files are copied from storage objects, sorted by `file_path`, and written as a new Java-compatible package/bundle under the target version. |
| Vite proxy boundary | planned | Only rerelease POST routes move to Python. Admin hide/unhide and yank stay Java-owned. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite success behavior, DB/file/audit effects, duplicate target rejection, and adjacent Java-owned route boundaries. |

## TDD Steps

- [x] Add failing Python tests for rerelease rebuild and workflow behavior.
- [x] Run the new test file and confirm it fails before implementation.
- [x] Implement minimal Python rerelease workflow and route adapter.
- [x] Add failing Vite proxy tests for rerelease ownership and adjacent boundary checks.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for rerelease.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [x] Commit and push to `dev`.

## Acceptance Criteria

- Public source version rerelease creates a target version using copied file entries and rewritten
  `SKILL.md` version.
- Private skill rerelease returns Java-compatible `UPLOADED`; public/namespace-visible skills follow
  publish workflow review/scanning behavior.
- Duplicate target version returns Java-compatible error before mutation.
- `confirmWarnings` is passed into publish validation/orchestration semantics where warnings exist.
- Vite proxy routes both rerelease aliases to Python while admin hide/unhide and yank remain Java.
- No files under `server/` are modified.
