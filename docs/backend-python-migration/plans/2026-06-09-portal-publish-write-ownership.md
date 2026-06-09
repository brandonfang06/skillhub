# Portal Publish Write Ownership Plan

## Summary

Move portal publish write aliases from Java to Python:

- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`

Both aliases will reuse the existing Python publish service path that already powers CLI publish
write ownership.

## Route Ownership

Change:

- `POST /api/v1/skills/{namespace}/publish`: `java` -> `python`
- `POST /api/web/skills/{namespace}/publish`: `java` -> `python`

Unchanged:

- `POST /api/cli/v1/skills/{namespace}/publish`: `python`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`: `python`
- `POST /api/v1/skills`: `java`
- `POST /api/v1/publish`: `java`
- `/oauth2/**`: `java`

## Scope

Allowed:

- `server-python/app/api/publish.py`
- publish HTTP tests
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- migration docs under `docs/backend-python-migration/`

Forbidden:

- Any changes under `server/`.
- ClawHub root publish ownership (`POST /api/v1/skills`).
- Legacy publish ownership (`POST /api/v1/publish`).
- OAuth/session/API-token migration.
- Scanner result consumer implementation.

## Java Parity Checklist

Reference:

- Java publish controller aliases for portal v1/web publish.
- `SkillPublishService` for publish behavior.

Covered by prior publish milestones:

- package extraction and validation
- dry-run preflight
- DB write transaction and rollback
- local object storage write
- review/security/scanner handoff side effects
- same-version replacement
- pending-review auto-withdraw
- CLI publish ownership through Vite

This milestone adds:

- Python route aliases for portal v1/web publish.
- Vite ownership for portal v1/web publish aliases.
- Live portal publish matrix proving both aliases write through Python while root/legacy publish
  remain Java-owned.

## Implementation Plan

1. Add failing route tests for `/api/v1/skills/{namespace}/publish` and
   `/api/web/skills/{namespace}/publish`.
2. Refactor Python publish route handler minimally so CLI/v1/web aliases share the same internal
   implementation.
3. Add Vite proxy entries for both portal publish aliases before `/api` fallback.
4. Update Vite proxy tests and route registry.
5. Add Windows live gate matrix:
   - publish through `/api/v1/skills/global/publish` via Vite
   - publish through `/api/web/skills/global/publish` via Vite
   - verify DB rows and statuses
   - verify root ClawHub publish and legacy publish still match Java
   - run Playwright smoke
6. Record result and commit/push.

## Acceptance Criteria

- `cd server-python; uv run pytest tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q` passes.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts` passes.
- Windows live gate `verify-portal-publish-write-ownership-smoke` passes.
- `git diff --name-only -- server` is empty.
