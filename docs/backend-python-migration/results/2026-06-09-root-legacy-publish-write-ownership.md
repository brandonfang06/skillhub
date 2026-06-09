# Root And Legacy Publish Write Ownership Result

## Summary

Moved the remaining ClawHub-compatible publish write routes to Python:

- `POST /api/v1/skills`
- `POST /api/v1/publish`

Both routes now go through Vite to FastAPI on port `8081` and reuse the existing Python publish
orchestration for DB writes, local storage, replacement cleanup, pending-review behavior, scanner
handoff, and side effects.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills` | Java | Python |
| POST | `/api/v1/publish` | Java | Python |
| DELETE | `/api/v1/skills/{canonicalSlug}` | Java | Java |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | Java | Java |

## Implemented

- Added FastAPI handlers for:
  - legacy zip publish: multipart `file` plus `namespace`;
  - root ClawHub publish: `payload` JSON plus repeated `files` parts.
- Preserved Java-compatible plain ClawHub response shape:
  `{ "ok": true, "skillId": "...", "versionId": "..." }`.
- Added namespace resolution parity for root payload publish:
  `payload.namespace` -> canonical `payload.slug` prefix -> `global`.
- Updated Vite proxy ownership for exact root/legacy publish paths.
- Updated older publish live gates so they check still-deferred delete/undelete boundaries instead
  of stale root/legacy Java-owned assumptions.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q
```

Result: `16 passed, 1 warning`.

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `19 passed`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-root-legacy-publish-write-ownership-smoke
```

Result:

- Python/server tests: `16 passed`.
- Vite proxy tests: `19 passed`.
- Live publish checks:
  - `/api/v1/publish` through Vite returned `200` with plain ClawHub response.
  - `/api/v1/skills` through Vite returned `200` with plain ClawHub response.
  - both writes created `PENDING_REVIEW` versions in `global`;
  - both writes created one pending review task;
  - delete and undelete compatibility routes still matched Java fallback status.
- Playwright smoke: `6 passed`.

Port cleanup was checked after the live gate; no listeners remained on `3000`, `8080`, `8081`, or
`8000`.

## Risks

- `confirmWarnings` is accepted for Java wire compatibility, but Python warning confirmation still
  depends on the existing dry-run/publish validation behavior. If Java has warning-only cases that
  are not yet represented in Python dry-run tests, add those before changing warning semantics.
- Root payload/files upload now supports the Java multipart shape used by the current compatibility
  service, but any undocumented client-specific payload fields beyond namespace/slug are still
  passed only as compatibility audit metadata through the existing publish flow.

## Follow-Up

- Next likely milestone: scanner result processing and status transitions after Redis handoff.
- Lifecycle/governance mutations should remain Java-owned until their own route-specific plan and
  live gate are added.
