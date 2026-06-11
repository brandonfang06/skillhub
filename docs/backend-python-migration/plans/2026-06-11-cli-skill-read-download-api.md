# CLI Skill Read And Download API Migration Plan

Date: 2026-06-11

## Milestone

Move the CLI skill read/download compatibility routes from Java to Python:

- `GET /api/cli/v1/skills/search`
- `GET /api/cli/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/cli/v1/skills/{namespace}/{slug}/download`
- `GET /api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download`

This milestone does not move the destructive CLI delete route:

- `DELETE /api/cli/v1/skills/{namespace}/{slug}`

## Java Contract

Reference implementation:

- `CliSkillController`
- `CliSkillAppService.search`
- `CliSkillAppService.resolve`
- `CliSkillAppService.downloadLatest`
- `CliSkillAppService.downloadVersion`

Required behavior:

- CLI search returns Java `ApiResponse` envelope with `{ items, total, limit }`.
- CLI search delegates to the same public search model as portal search with `page = 0`, `sort = newest`, no namespace, no labels.
- CLI search item fields are `{ namespace, slug, latestVersion, summary }`.
- CLI resolve returns Java `ApiResponse` envelope with `{ namespace, slug, version, versionId, fingerprint, downloadUrl }`.
- CLI download routes stream the same package content and headers as the migrated portal download routes.
- CLI download routes accept anonymous public downloads and authenticated visibility context through `X-Mock-User-Id`.

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| Controller / service references | covered | `CliSkillController` and `CliSkillAppService` define the read/download contract. |
| API contract | covered | Search/resolve use Java `ApiResponse`; download returns stream/redirect response. |
| Authorization / visibility | covered | Read/download reuse the migrated Python search, resolve, and download visibility behavior. |
| Database transaction atomicity | not applicable | Search/resolve are reads; download counter increments reuse the existing Python download transaction. |
| Audit / side effects | not applicable | Java CLI read/download routes do not write audit logs. |
| Storage / external services | covered | Download routes reuse the existing Python download service and storage-base behavior. |
| Live verification evidence | planned | `verify-cli-skill-read-download-smoke` compares Java/Python/proxy search, resolve, download bytes/headers, and delete boundary. |

## Route Ownership

Move these method-aware routes to Python:

- `GET /api/cli/v1/skills/search`
- `GET /api/cli/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/cli/v1/skills/{namespace}/{slug}/download`
- `GET /api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download`

Keep Java-owned:

- `DELETE /api/cli/v1/skills/{namespace}/{slug}`
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

- `cd server-python; uv run pytest tests/test_cli_skills.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`

Live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-cli-skill-read-download-smoke`

Mandatory safety checks:

- `git diff --name-only -- server` must be empty.
- `git diff --check` must pass.
