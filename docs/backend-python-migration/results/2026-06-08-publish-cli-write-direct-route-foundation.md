# Publish CLI Write Direct Route Foundation Result

## Summary

Implemented a direct Python backend route for:

- `POST /api/cli/v1/skills/{namespace}/publish`

This milestone intentionally did not move Vite proxy ownership. The write route remains Java-owned
through the frontend/proxy path while Python can be called directly on port `8081` for parity
development and live DB/storage validation.

## Routes Changed

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java-owned | Java-owned through proxy; direct Python implementation exists on `8081` |

## Implemented

- Added Python multipart publish write route with local `X-Mock-User-Id` auth bridge.
- Reused dry-run preflight before write; invalid preflight aborts before DB/storage mutation.
- Built `PublishWriteInput` from namespace context, package metadata, visibility, request metadata,
  and platform roles.
- Reused publish orchestration for DB prepare, local storage write, DB finalize, and side effects.
- Added Windows live gate `verify-publish-cli-write-direct-smoke`.
- Fixed live PostgreSQL/asyncpg JSONB encoding by serializing `parsed_metadata_json` and
  `manifest_json` SQL parameters at the DB boundary.

## Verification

Commands:

- `cd server-python; uv run pytest tests/test_publish_transaction.py tests/test_publish_orchestration.py tests/test_publish_http_validate.py -q`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-cli-write-direct-smoke`

Results:

- Narrow Python tests: `19 passed, 1 warning`.
- Windows live gate:
  - Python route tests: `74 passed, 1 warning`.
  - Java direct publish write: HTTP `200`.
  - Python direct publish write: HTTP `200`.
  - Stable response fields matched: `status`, `code`, `data.namespace`, `data.version`,
    `data.visibility`.
  - Proxy ownership check matched Java: proxy returned Java-equivalent `401` for unauthenticated
    write route, proving Vite still routes this write path to Java.
  - Playwright smoke: `6 passed`.

## Deferred Before Ownership Move

- Scanner HTTP handoff and scanner failure behavior.
- Route-level same-version replacement lookup and cleanup.
- Pending-review auto-withdraw before creating a replacement version.
- Storage-failure cleanup evidence for the HTTP route.
- Repeated publish live matrix against Java.

## Server Directory Guard

`server/` remained unmodified for this milestone.
