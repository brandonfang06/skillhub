# My Skills API Migration Plan

**Date:** 2026-06-10

**Goal:** Move current-user owned skill list routes from Java to FastAPI.

**Milestone group:** Group F/G boundary - current-user dashboard reads.

## Route Ownership

Move to Python:

- `GET /api/v1/me/skills`
- `GET /api/web/me/skills`

Remain Java-owned:

- Other `/api/v1/me/**` or `/api/web/me/**` routes not already listed as Python-owned.

## Java Contract

Reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/MeController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/MySkillAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/JpaMySkillQueryRepository.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillLifecycleProjectionService.java`

Contract:

- Routes require authenticated local user context.
- Defaults: `page=0`, `size=10`.
- Query parameters: `filter`, `q`, `namespace`.
- Invalid/blank filter falls back to `ALL`.
- No filter/q/namespace path uses direct owner pagination and includes all owned skills, including
  archived/hidden, ordered by `updated_at DESC`.
- Filter path applies Java `matchesFilter` behavior:
  - `ALL` excludes hidden and archived.
  - `ARCHIVED` returns archived, non-hidden skills.
  - `HIDDEN` returns hidden skills only for `SUPER_ADMIN`; non-admin users see none.
  - `PENDING_REVIEW` and `REJECTED` use owner preview version status.
  - `PUBLISHED` requires a published version.
- `q` matches display name, slug, or summary case-insensitively.
- `namespace` filters by namespace slug.
- Response is `PageResponse<SkillSummaryResponse>` with owner summary lifecycle projections.

## Python Implementation Boundaries

Allowed edits:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden edits:

- Any file under `server/`.
- Generated frontend API types.

## Data Access Strategy

Use explicit `sqlalchemy.text` SQL against Java-owned tables. Do not introduce ORM models or schema
migrations.

## Testing Plan

- Add failing Python tests for:
  - default owner list includes archived/hidden and uses `size=10`,
  - keyword/namespace path filters out hidden/archived for `ALL`,
  - `HIDDEN` requires `SUPER_ADMIN`,
  - owner preview and published lifecycle summary fields,
  - route envelopes and auth boundaries.
- Add failing Vite proxy tests for `GET /api/v1|web/me/skills`.
- Add Windows live gate:
  - seed owned skills with published, pending, hidden, and archived states,
  - compare Java/Python/Vite stable JSON for default, keyword/namespace, and hidden admin cases,
  - verify anonymous rejection,
  - run Playwright smoke.

## Checklist

- [x] Add failing Python my-skills tests.
- [x] Implement Python owned skill list service/routes.
- [x] Add failing Vite proxy tests.
- [x] Route my-skills GET to Python.
- [x] Add Windows live gate.
- [x] Update route registry and sequence plan.
- [x] Run narrow tests.
- [x] Run Windows live gate.
- [x] Confirm `git diff --name-only -- server` is empty.
- [x] Write result document.
- [x] Commit and push.
