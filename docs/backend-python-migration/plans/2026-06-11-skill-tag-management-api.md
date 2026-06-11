# Skill Tag Management API Migration Plan

Date: 2026-06-11

## Milestone

Move portal skill tag management routes from Java to Python:

- `GET /api/v1/skills/{namespace}/{slug}/tags`
- `GET /api/web/skills/{namespace}/{slug}/tags`
- `PUT /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `PUT /api/web/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/web/skills/{namespace}/{slug}/tags/{tagName}`

Already Python-owned tag file/download routes are not changed in this milestone.

## Java Contract

Reference implementation:

- `SkillTagController`
- `SkillTagService`
- `TagRequest`
- `TagResponse`

Required behavior:

- List tags returns Java `ApiResponse<List<TagResponse>>` with the live Java success message
  `获取成功`.
- List tags enforces skill visibility through Java `VisibilityChecker.canAccess` behavior.
- List tags includes persisted tags and appends a virtual `latest` tag when `skill.latest_version_id`
  exists.
- PUT requires current user and namespace `OWNER` or `ADMIN` membership.
- PUT rejects reserved `latest` tag name case-insensitively with
  `error.skill.tag.latest.reserved`.
- PUT resolves the target skill with current-user slug preference, requires target version to
  exist, and requires target version status `PUBLISHED`.
- PUT creates a new tag or moves an existing tag to the target version.
- DELETE requires current user and namespace `OWNER` or `ADMIN` membership.
- DELETE rejects deleting reserved `latest` case-insensitively with
  `error.skill.tag.latest.delete`.
- PUT returns the live Java success message `更新成功`.
- DELETE rejects missing tags with `error.skill.tag.notFound` and returns the live Java success
  message `删除成功` with `{ message: "Tag deleted" }`.

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| Controller / service references | covered | `SkillTagController` and `SkillTagService` define the route contract. |
| API contract | covered | `TagResponse` is `{ id, tagName, versionId, createdAt }`; delete returns `MessageResponse`. |
| Authorization / visibility | covered | List uses visibility access; writes require namespace `OWNER` or `ADMIN`. |
| Database transaction atomicity | covered | PUT/DELETE use one Python DB transaction via `engine.begin()`. |
| Audit / side effects | not applicable | Java tag service does not write audit logs. |
| Storage / external services | not applicable | Tag management mutates only `skill_tag`. |
| Live verification evidence | planned | `verify-skill-tag-management-smoke` compares Java/Python/proxy list/create/move/delete and tag file route boundaries. |

## Route Ownership

Move these method-aware routes to Python:

- `GET /api/v1/skills/{namespace}/{slug}/tags`
- `GET /api/web/skills/{namespace}/{slug}/tags`
- `PUT /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `PUT /api/web/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/web/skills/{namespace}/{slug}/tags/{tagName}`

Keep Java-owned:

- skill hard delete routes
- device/OAuth/session routes
- unlisted `/api/**`
- `/oauth2/**`

## Implementation Boundary

Allowed:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden:

- `server/`
- generated OpenAPI files
- broad frontend behavior changes

## Verification

Narrow tests:

- `cd server-python; uv run pytest tests/test_skill_tags.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`

Live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-tag-management-smoke`

Mandatory safety checks:

- `git diff --name-only -- server` must be empty.
- `git diff --check` must pass.
