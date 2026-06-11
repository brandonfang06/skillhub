# CLI Skill Read And Download API Migration Result

Date: 2026-06-11

## Summary

Moved CLI skill read/download compatibility routes to Python while keeping the destructive CLI delete
route Java-owned.

## Route Ownership

Moved to Python:

- `GET /api/cli/v1/skills/search`
- `GET /api/cli/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/cli/v1/skills/{namespace}/{slug}/download`
- `GET /api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download`

Still Java-owned:

- `DELETE /api/cli/v1/skills/{namespace}/{slug}`
- unlisted `/api/**`
- `/oauth2/**`

## Implementation Notes

- Added Python CLI search and resolve adapters over the already migrated skill search/resolve read
  paths.
- Search returns Java-compatible `ApiResponse` data `{ items, total, limit }`.
- Resolve returns Java-compatible flat `ApiResponse` data `{ namespace, slug, version, versionId,
  fingerprint, downloadUrl }`.
- CLI download routes are thin wrappers over the migrated portal latest/version download handlers,
  preserving stream bytes, headers, visibility behavior, and published counter updates.
- Vite proxy ownership is method-aware so only the selected CLI GET routes move to Python.

## Verification

Narrow tests:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_cli_skills.py tests/test_hybrid_makefile.py -q`
  - Result: `10 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `43 passed`

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-cli-skill-read-download-smoke`
  - Python tests: `10 passed`
  - Vite proxy tests: `43 passed`
  - Playwright smoke: `6 passed`
  - Java/Python/proxy contract checks:
    - `searchEnvelopeMatches: true`
    - `resolveEnvelopeMatches: true`
    - `latestDownloadMatches: true`
    - `versionDownloadMatches: true`
    - `deleteRemainsJavaOwned: true`

Safety checks:

- `git diff --name-only -- server`: no output
- `git diff --check`: passed

## Risks And Follow-Up

- CLI destructive delete remains Java-owned and should move only with the final destructive-route
  and auth/session parity work.
- Final proxy cleanup is still deferred until all remaining route ownership is known.
- The live download comparison uses a deterministic public fixture and compares fallback zip entries
  for the version download path.
