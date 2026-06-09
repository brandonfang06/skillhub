# Skill Rerelease API Migration Result

## Summary

Moved portal skill version rerelease ownership to Python:

- `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`
- `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`

Admin hide/unhide, yank, and any unlisted lifecycle/governance routes remain Java-owned.

## Implementation Notes

- Added `SkillRereleaseInput` and `rerelease_skill_version`.
- Reads the source skill/version through existing lifecycle SQL helpers.
- Requires owner or namespace `OWNER`/`ADMIN`.
- Requires source version status `PUBLISHED`.
- Rejects duplicate target version before publish write.
- Rebuilds package entries from source `skill_file.storage_key` local objects sorted by path.
- Rewrites `SKILL.md` frontmatter `version` to the trimmed target version.
- Runs package validation and honors `confirmWarnings` for warning confirmation.
- Delegates target version creation/storage/side effects to existing Python publish orchestration.
- Writes `RERELEASE_SKILL_VERSION` lifecycle audit on the source version inside the publish
  orchestration transaction callback.
- Vite method-aware proxy now routes both rerelease POST aliases to Python.

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | Covered: request body uses `targetVersion` and `confirmWarnings`; response action is `RERELEASE_VERSION` in the update-success envelope. |
| Authorization/session | Covered for local bridge: mock user is required, and owner or namespace manager can rerelease. |
| Database transaction atomicity | Covered: target version/storage/side effects and lifecycle audit use the publish orchestration transaction callback for the actual route path. |
| Audit actor/timestamp fields | Covered: `RERELEASE_SKILL_VERSION` audit targets the source version and stores `sourceVersion`/trimmed `targetVersion`. |
| Storage and side effects | Covered: source objects are copied, target `SKILL.md` version is rewritten, and target objects/bundle use existing Java-compatible publish storage keys. |
| Vite proxy boundary | Covered: rerelease POST routes are Python-owned; admin hide/unhide and yank remain Java-owned/fallback. |
| Live verification evidence | Covered: Windows live gate passed for Java/Python/Vite response parity, DB state, audit, storage rewrite, duplicate target rejection, unauth rejection, admin hide/yank Java-owned boundaries, and Playwright smoke. |

## Verification

- Red checks:
  - `uv run pytest tests/test_skill_lifecycle_rerelease.py -q` initially failed because `SkillRereleaseInput` was missing.
  - `npx.cmd vitest run vite.config.test.ts` initially failed because rerelease proxy ownership was still undefined.
- Narrow checks after implementation:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_rerelease.py tests/test_hybrid_makefile.py -q`
    - Result: 13 passed, 1 warning.
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_lifecycle_rerelease.py tests/test_publish_orchestration.py tests/test_hybrid_makefile.py -q`
    - Result: 20 passed, 1 warning.
  - `cd web; npx.cmd vitest run vite.config.test.ts`
    - Result: 23 passed.
  - `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[void][scriptblock]::Create((Get-Content -Raw -LiteralPath 'scripts\dev-hybrid.ps1')); 'syntax-ok'"`
    - Result: `syntax-ok`.

Windows live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-skill-rerelease-smoke
```

Result:

- Python/live-gate pytest suite: 47 passed, 1 warning.
- Vite proxy test: 23 passed.
- Contract checks:
  - `responsesMatch: true`
  - `dbState: true`
  - `audit: true`
  - `storageVersionRewritten: true`
  - `duplicateTargetRejected: true`
  - `unauthenticatedRereleaseRejected: true`
  - `adminYankStillJavaOwned: true`
  - `adminHideStillJavaOwned: true`
- Stable status: Java/Python/Vite/Web all returned `RERELEASE_VERSION` with `PENDING_REVIEW`.
- Playwright smoke: 6 passed.

## Risks And Follow-Up

- Rerelease uses local storage bridge behavior already established for publish/download. S3/MinIO
  object storage abstraction remains a broader storage parity follow-up.
