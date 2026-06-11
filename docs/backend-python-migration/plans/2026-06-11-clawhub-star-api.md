# ClawHub Star Compatibility API Migration Plan

Date: 2026-06-11

## Milestone

Move the ClawHub compatibility star/unstar routes from Java to Python:

- `POST /api/v1/stars/{canonicalSlug}`
- `DELETE /api/v1/stars/{canonicalSlug}`

This milestone does not take over skill hard delete, undelete, OAuth/session flows, or any new
portal social routes.

## Java Contract

Reference implementation:

- `ClawHubCompatController.starSkill`
- `ClawHubCompatController.unstarSkill`
- `ClawHubCompatAppService.starSkill`
- `ClawHubCompatAppService.unstarSkill`
- `CanonicalSlugMapper`

Required behavior:

- `canonicalSlug` maps to `(namespace, slug)` by splitting on the first `--`; no separator means
  namespace `global`.
- The target skill must be resolved through the visible skill path before mutation.
- Authenticated user is required.
- `POST` is idempotent:
  - first call returns `{ ok: true, starred: true, alreadyStarred: false }`
  - repeated call returns `{ ok: true, starred: true, alreadyStarred: true }`
- `DELETE` is idempotent:
  - first call returns `{ ok: true, unstarred: true, alreadyUnstarred: false }`
  - repeated call returns `{ ok: true, unstarred: true, alreadyUnstarred: true }`
- Response is plain ClawHub JSON, not the SkillHub `ApiResponse` envelope.
- `skill.star_count` must stay synchronized with `skill_star`.

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| Controller / service references | covered | `ClawHubCompatController`, `ClawHubCompatAppService`, `CanonicalSlugMapper`, and `SkillStarService` are the reference sources. |
| API contract | covered | Preserve plain ClawHub response bodies and idempotent `already*` flags. |
| Authorization / visibility | covered | Require authenticated user and reuse visible skill access semantics before mutation. |
| Database transaction atomicity | covered | Resolve target, check current star state, mutate `skill_star`, and refresh `skill.star_count` inside one transaction. |
| Audit / side effects | not applicable | Java ClawHub star/unstar does not write audit logs. |
| Storage / external services | not applicable | No object storage or scanner interaction. |
| Live verification evidence | covered | `verify-clawhub-star-smoke` compares Java, Python, and Vite proxy first/repeated star/unstar responses plus DB state. |

## Route Ownership

Move only these route patterns to Python in Vite method-aware proxy:

- `POST /api/v1/stars/{canonicalSlug}` -> `localhost:8081`
- `DELETE /api/v1/stars/{canonicalSlug}` -> `localhost:8081`

Keep these nearby routes Java-owned:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- any `/oauth2/**`
- unlisted `/api/**`

## Implementation Boundary

Allowed:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden:

- `server/`
- broad frontend behavior changes
- generated OpenAPI files

## Verification

Narrow tests:

- `cd server-python; uv run pytest tests/test_clawhub_star.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`

Live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-star-smoke`

Mandatory safety checks:

- `git diff --name-only -- server` must be empty.
- `git diff --check` must pass.
