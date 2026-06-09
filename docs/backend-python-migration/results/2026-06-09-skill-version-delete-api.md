# Skill Version Delete API Result

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| DELETE | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | java / proxy-boundary ambiguous | python |
| DELETE | `/api/web/skills/{namespace}/{slug}/versions/{version}` | java | python |

Still Java-owned:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`
- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/v1/skills/{namespace}/{slug}/submit-review`
- `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`
- `/api/v1/admin/skills/**` hide/unhide/yank

## Implementation

- Added `SkillVersionDeleteInput`, `SkillVersionDeleteResult`, and `delete_skill_version(...)`.
- Added v1/web DELETE aliases in `server-python/app/api/lifecycle.py`.
- Added method-aware Vite DELETE rules for version delete.
- Added Windows live gate `verify-skill-version-delete-smoke`.
- Updated route registry and migration sequence plan.
- Fixed Python DB scanner type parity:
  - `security_audit.scanner_type` now stores/queries Java enum DB value `SKILL_SCANNER`.
  - Redis scan task metadata still uses external value `skill-scanner`.

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | covered. Java/Python/Vite stable response fields matched. |
| Authorization/session | covered for local bridge. Routes require `X-Mock-User-Id`; tests cover owner/namespace manager permission through shared lifecycle logic. |
| Database transaction atomicity | covered. Eligibility check, last-version guard, latest recalculation, file metadata delete, security audit soft-delete, version delete, and audit insert happen in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered. Python writes `DELETE_SKILL_VERSION` on `SKILL_VERSION` with `{"version":"1.1.0"}` detail. |
| Storage and side effects | covered for local storage. Python deletes collected local object keys after DB commit and records compensation if deletion fails. S3/MinIO abstraction remains later work. |
| Live verification evidence | covered by Windows live gate. |

## Verification

- Red tests:
  - `uv run pytest tests/test_skill_lifecycle_delete_version.py -q` initially failed because `SkillVersionDeleteInput` did not exist.
  - `npx.cmd vitest run vite.config.test.ts` initially failed because DELETE version method-aware ownership was undefined.
- Narrow green tests:
  - `UV_CACHE_DIR=...\skillhub\.uv-cache; uv run pytest tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_archive.py tests/test_hybrid_makefile.py tests/test_publish_side_effects.py tests/test_publish_scanner_result.py -q`
  - Result: `32 passed, 1 warning`.
  - `npx.cmd vitest run vite.config.test.ts`
  - Result: `23 passed`.
- Windows live gate:
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-version-delete-smoke`
  - Result: passed.
  - Python/Vite prechecks: `17 passed`, `23 passed`.
  - Java/Python/Vite stable responses matched.
  - DB checks passed: version row deleted, skill_file rows deleted, security_audit soft-deleted, latest pointer recalculated to the published version.
  - Audit checks passed.
  - Local storage delete checks passed.
  - Boundary checks passed: rerelease and submit-review still route like Java; unauthenticated delete returns `401`.
  - Playwright smoke: `6 passed`.
- Post-gate status:
  - `scripts\dev-hybrid.ps1 status`
  - Java backend stopped, Python backend stopped, Vite frontend stopped.

## Notes And Risks

- The first live gate attempt failed on Java direct with `No enum constant ... ScannerType.skill-scanner`.
  Root cause: Python-side fixtures and publish side effects used the external scanner value
  `skill-scanner` in the DB enum column. The fix stores/queries `SKILL_SCANNER` for DB rows while
  preserving `skill-scanner` in Redis scan task payloads.
- Physical storage deletion is implemented for local storage. A later storage abstraction should map
  the same delete/compensation contract to MinIO/S3 before production storage is enabled.

## Follow-Up

- Continue lifecycle migration with either withdraw-review or submit-review/confirm-publish.
- Consider a targeted scanner DB enum regression gate if future reviewer feedback focuses on scanner
  parity.
