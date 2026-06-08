# Publish Scanner Handoff Foundation Result

## Summary

Implemented Python scanner handoff foundation for publish write orchestration without moving route
ownership.

Java scanner handoff publishes asynchronous scan tasks to Redis Stream
`skillhub:scan:requests`; it does not synchronously call the scanner HTTP API from the publish
request path. Python now mirrors that handoff shape when scanner is explicitly enabled.

## Routes Changed

No route ownership changed.

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java-owned through proxy; direct Python route existed | Same ownership; direct Python route can publish scanner handoff when enabled |

## Implemented

- Added scanner settings:
  - `SKILLHUB_SECURITY_SCANNER_ENABLED`
  - `SKILLHUB_SECURITY_SCANNER_MODE`
  - `SKILLHUB_REDIS_URL`
  - `SKILLHUB_SCAN_STREAM_KEY`
- Added dependency-free Redis Stream `XADD` publisher for scan tasks.
- Wired scanner-enabled direct Python publish to call scan task publisher.
- Matched Java scan task fields:
  - `taskId`
  - `versionId`
  - `bundleKey` in upload mode
  - `publisherId`
  - `createdAtMillis`
  - `scannerType=skill-scanner`
- Generated UUID task IDs when no explicit task ID is provided.
- Fixed live PostgreSQL/asyncpg JSONB encoding for:
  - `security_audit.findings`
  - `audit_log.detail_json`

## Verification

Commands:

- `cd server-python; uv run pytest tests/test_publish_scanner_handoff.py tests/test_publish_orchestration.py tests/test_publish_side_effects.py tests/test_publish_http_validate.py tests/test_config.py tests/test_hybrid_makefile.py -q`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scanner-handoff-smoke`

Results:

- Narrow Python tests: `33 passed, 1 warning`.
- Windows live gate:
  - Python scanner handoff tests: `27 passed, 1 warning`.
  - Direct Python publish: HTTP `200`.
  - Redis stream entry present in `skillhub:scan:requests`.
  - Redis fields checked:
    `taskId`, `versionId`, `bundleKey`, `publisherId`, `createdAtMillis`, `scannerType`.
  - Upload mode used `bundleKey` and no `skillPath`.
  - `scannerType` matched `skill-scanner`.
  - Playwright smoke: `6 passed`.

## Deferred

- Scanner consumer/result processing.
- Retry/reclaim behavior.
- Scanner HTTP adapter parity from the consumer side.
- Same-version replacement lookup from the HTTP route.
- Pending-review auto-withdraw before replacement.
- Storage-failure cleanup evidence for HTTP route ownership.
- Repeated publish live matrix against Java.

## Server Directory Guard

`server/` remained unmodified for this milestone.
