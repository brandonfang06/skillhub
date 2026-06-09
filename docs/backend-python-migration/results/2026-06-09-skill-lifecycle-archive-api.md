# Skill Lifecycle Archive API Result

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills/{namespace}/{slug}/archive` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/archive` | java | python |
| POST | `/api/v1/skills/{namespace}/{slug}/unarchive` | java | python |
| POST | `/api/web/skills/{namespace}/{slug}/unarchive` | java | python |

Still Java-owned:

- `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`
- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`
- `/api/v1/admin/skills/**` hide/unhide/yank

## Implementation

- Added `server-python/app/lifecycle/skill.py` for archive/unarchive workflow.
- Added `server-python/app/api/lifecycle.py` for v1/web route aliases.
- Registered the lifecycle router in `server-python/app/main.py`.
- Added method-aware Vite proxy rules for only archive/unarchive POST aliases.
- Added Windows live gate `verify-skill-lifecycle-archive-smoke`.
- Updated route registry and migration sequence plan.

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | covered. Java/Python/Vite stable response fields matched for archive and unarchive. |
| Authorization/session | covered for local bridge. Routes require `X-Mock-User-Id`; unit tests cover owner and namespace manager permission. |
| Database transaction atomicity | covered. Python updates `skill` and inserts `audit_log` in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered. Python writes `ARCHIVE_SKILL`/`UNARCHIVE_SKILL`, actor, request id, IP, user-agent, and reason detail for archive. |
| Storage and side effects | deferred. Java publishes status-change events; Python does not yet implement async search/event listeners for lifecycle status changes. |
| Live verification evidence | covered by Windows live gate. |

## Verification

- Red tests:
  - `uv run pytest tests/test_skill_lifecycle_archive.py -q` initially failed with `ModuleNotFoundError: No module named 'app.lifecycle'`.
  - `npx.cmd vitest run vite.config.test.ts` initially failed because archive proxy ownership returned `undefined`.
- Narrow green tests:
  - `UV_CACHE_DIR=...\skillhub\.uv-cache; uv run pytest tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py -q`
  - Result: `11 passed, 1 warning`.
  - `npx.cmd vitest run vite.config.test.ts`
  - Result: `22 passed`.
- Windows live gate:
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-lifecycle-archive-smoke`
  - Result: passed.
  - Python/Vite prechecks: `11 passed`, `22 passed`.
  - Java/Python/Vite stable archive responses matched.
  - Java/Python/Vite stable unarchive responses matched.
  - DB checks passed: `archiveDbState`, `unarchiveDbState`.
  - Audit checks passed: `archiveAudit`, `unarchiveAudit`.
  - Boundary checks passed: `rereleaseBoundaryJavaOwned`, `unauthenticatedArchiveRejected`.
  - Playwright smoke: `6 passed`.
- Post-gate status:
  - `scripts\dev-hybrid.ps1 status`
  - Java backend stopped, Python backend stopped, Vite frontend stopped.

## Notes And Risks

- The first live attempt used a namespace admin who was not the skill owner. Java's
  `SkillSlugResolutionService.Preference.CURRENT_USER` returned not found for that direct Java
  fixture. The live gate now uses the owner actor for direct Java/Python/Vite comparison; Python
  unit tests still cover namespace `ADMIN` permission.
- Existing Vite static proxy rules for version detail can route
  `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}` to Python and return `405` while
  Java direct returns `401` without auth. This predates this milestone and is not expanded here.
  The archive/unarchive milestone keeps DELETE version unowned in method-aware tests and records the
  live observation for a later proxy-boundary cleanup.

## Follow-Up

- Migrate the next lifecycle slice separately: likely submit-review/confirm-publish or
  withdraw-review, depending on how much overlap we want with the already-migrated review routes.
- Plan a later lifecycle event/search side-effect milestone for Java status-change event parity.
