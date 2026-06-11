# Skill Tag Management API Migration Result

Date: 2026-06-11

## Summary

Moved portal skill tag management routes to Python while preserving Java tag visibility, write
authorization, reserved tag handling, and live success-message behavior.

## Route Ownership

Moved to Python:

- `GET /api/v1/skills/{namespace}/{slug}/tags`
- `GET /api/web/skills/{namespace}/{slug}/tags`
- `PUT /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `PUT /api/web/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `DELETE /api/web/skills/{namespace}/{slug}/tags/{tagName}`

Still Java-owned/deferred:

- skill hard delete routes
- device/OAuth/session routes
- unlisted `/api/**`
- `/oauth2/**`

## Implementation Notes

- Tag list uses the migrated Python visibility helpers and appends Java's virtual `latest` tag when
  `skill.latest_version_id` exists.
- Tag list and writes preserve Java `SkillSlugResolutionService.Preference.CURRENT_USER` behavior by
  preferring the current user's same-slug skill before falling back to the published visible skill.
- Tag create/move and delete use one `engine.begin()` transaction each.
- Tag write routes require current user and namespace `OWNER` or `ADMIN` membership.
- `latest` is reserved case-insensitively for create/move and delete.
- Create/move requires the target version to exist and have `PUBLISHED` status.
- Live verification caught a message parity issue; Python now returns the live Java success messages
  `获取成功`, `更新成功`, and `删除成功` for these routes.
- Live verification also caught an asyncpg parameter typing issue in the current-user preference SQL;
  the nullable current user bind is explicitly cast to `varchar`.

## Verification

TDD red gate:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_tags.py -q`
  - Initial result: failed with missing route/helper coverage (`404` and missing attributes).

Narrow tests:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_tags.py tests/test_hybrid_makefile.py -q`
  - Result: `12 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `44 passed`

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-tag-management-smoke`
  - Python tests: `12 passed`
  - Vite proxy tests: `44 passed`
  - Java/Python/proxy contract checks:
    - `listMatches: true`
    - `createMatches: true`
    - `moveMatches: true`
    - `deleteMatches: true`
    - `postBoundaryRemainsJavaOwned: true`
  - Playwright smoke: `6 passed`

Safety checks:

- `git diff --name-only -- server`: no output
- `git diff --check`: passed

## Risks And Follow-Up

- The live comparison normalizes generated tag IDs and timestamps because each Java/Python/proxy
  mutation comparison starts from a reset fixture and creates separate database rows.
- Final proxy cleanup remains deferred until remaining route ownership is complete.
