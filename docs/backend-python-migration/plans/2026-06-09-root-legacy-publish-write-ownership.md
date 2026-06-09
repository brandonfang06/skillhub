# Root And Legacy Publish Write Ownership Plan

## Milestone

Move the remaining ClawHub-compatible publish write routes to Python:

- `POST /api/v1/skills`
- `POST /api/v1/publish`

This milestone completes publish write route ownership for the currently implemented Python
publish path. It does not migrate delete/undelete, scanner result consumption, OAuth/session,
or lifecycle/governance mutations.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills` | java | python |
| POST | `/api/v1/publish` | java | python |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java | java |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java | java |

## Java Contract Notes

- `/api/v1/publish` accepts multipart `file`, form `namespace`, and optional
  `confirmWarnings`; it returns the plain ClawHub response `{ ok, skillId, versionId }`.
- `/api/v1/skills` accepts multipart `payload` JSON and repeated `files` parts. Namespace is
  resolved from `payload.namespace`, from canonical `payload.slug` when it contains `--`, or falls
  back to `global`.
- Both routes publish as `PUBLIC` and must reuse the existing Python publish transaction,
  storage, replacement, pending-review, scanner handoff, and audit behavior.
- These compatibility routes must not return the portal/CLI `ApiResponse` envelope.

## Implementation Scope

- `server-python/app/api/publish.py`
  - add root/legacy FastAPI handlers;
  - add payload/files multipart adapter;
  - share the existing publish write orchestration through a common helper.
- `web/vite.config.ts`
  - route exact root/legacy publish paths to Python before `/api` fallback.
- `scripts/dev-hybrid.ps1`
  - add Windows live gate for root/legacy ownership.
- Tests and migration docs.

## Verification

- `cd server-python; uv run pytest tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-root-legacy-publish-write-ownership-smoke`
- `git diff --name-only -- server` must be empty.

## Non-Goals

- No edits under `server/`.
- No delete/undelete route ownership changes.
- No scanner result consumer.
- No OAuth/session/API-token migration.
