# Skill Label Mutations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move skill label attach/detach routes to FastAPI and close the remaining skill-label ownership gap.

## Route Ownership

Move to Python:

- `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`

Already Python-owned:

- `GET /api/v1/labels`
- `GET /api/web/labels`
- `GET /api/v1/skills/{namespace}/{slug}/labels`
- `GET /api/web/skills/{namespace}/{slug}/labels`
- Admin label definition management under `/api/v1/admin/labels`.

## Java Parity Checklist

- Controller reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLabelController.java`
- App service reference: `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillLabelAppService.java`
- Domain service reference: `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/SkillLabelService.java`
- Permission reference: `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelPermissionChecker.java`

Behavior to preserve:

- Attach returns `SkillLabelDto`: `{ slug, type, displayName }` with message `response.success.updated`.
- Detach returns `MessageResponse("Label detached")` with message `response.success.deleted`.
- Missing auth returns 401.
- Non-owner/non-namespace-admin/non-super-admin returns `label.skill.no_permission`.
- `PRIVILEGED` labels can only be attached/detached by `SUPER_ADMIN`.
- `RECOMMENDED` labels can be attached/detached by skill owner, namespace `ADMIN`, namespace `OWNER`, or `SUPER_ADMIN`.
- Attach is idempotent for an existing `(skill_id, label_id)` pair.
- Attach rejects when the skill already has 10 labels.
- Detach rejects missing skill-label with `label.skill.not_found`.
- Both mutations write audit logs on target type `SKILL`:
  - `SKILL_LABEL_ATTACH`
  - `SKILL_LABEL_DETACH`
  - detail JSON keeps the request `labelSlug` value, matching Java string construction.

## Files

- Modify: `server-python/app/api/labels.py`
- Create: `server-python/tests/test_skill_label_mutations.py`
- Modify: `server-python/tests/test_hybrid_makefile.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vite.config.test.ts`
- Modify: `scripts/dev-hybrid.ps1`
- Modify: `docs/backend-python-migration/route-registry.md`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Create result: `docs/backend-python-migration/results/2026-06-10-skill-label-mutations.md`

## Tasks

- [x] Write pytest coverage for attach/detach DB effects, idempotency, max-label guard, permission rules, privileged-label guard, audit detail, and route envelopes.
- [x] Verify tests fail because mutation functions/routes do not exist.
- [x] Implement transactional Python attach/detach functions.
- [x] Add FastAPI PUT/DELETE routes with Java-compatible messages and request metadata.
- [x] Expand Vite method-aware proxy ownership for the four mutation routes.
- [x] Add Windows live gate fixture and Java/Python/proxy comparison for attach and detach.
- [x] Update route registry and migration sequence plan.
- [x] Run narrow Python tests, Vite proxy tests, Windows live gate, `git diff --name-only -- server`, and `git diff --check`.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_skill_label_mutations.py tests/test_labels.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-skill-label-mutation-smoke`
- `git diff --name-only -- server`
- `git diff --check`
