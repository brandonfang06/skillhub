# Publish Scanner Handoff Foundation Plan

## Summary

Add the Python-side scanner handoff foundation for publish write orchestration without moving route
ownership.

Java scanner handoff is asynchronous: `SecurityScanService.triggerScan(...)` creates a
`security_audit`, optionally moves non-published versions to `SCANNING`, and publishes a scan task
to Redis Stream `skillhub:scan:requests`. It does not synchronously call the scanner HTTP API from
the publish request path.

## Route Ownership

No route ownership changes.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Python direct route on port `8081` may use scanner handoff when explicitly enabled.
- Route registry remains unchanged.

## Scope

Allowed:

- `server-python/` scanner handoff adapter and tests.
- `scripts/dev-hybrid.ps1` Windows live gate additions.
- `docs/backend-python-migration/` plan/result/sequence updates.

Forbidden:

- Any changes under `server/`.
- Moving Vite proxy ownership for publish write routes.
- Scanner result processing, retry consumer, or notification delivery.

## Java Parity Checklist

Reference files:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityScanService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/ScanTask.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/RedissonScanTaskProducer.java`

Required behavior:

- Redis stream fields match Java producer:
  `taskId`, `versionId`, optional `skillPath`, optional `bundleKey`, `publisherId`,
  `createdAtMillis`, `scannerType`.
- `scannerType` remains `skill-scanner`.
- Upload mode publishes `bundleKey` and no `skillPath`.
- Local mode publishes `skillPath` and no `bundleKey`.
- Published versions remain `PUBLISHED`; non-published versions move to `SCANNING` as already
  covered by side-effect tests.

## Implementation Plan

1. Add failing orchestration test proving `scanner_enabled=True` requires a scan task publisher call.
2. Add a small Python Redis Stream publisher adapter using RESP/XADD, without adding a dependency.
3. Add settings for scanner enabled/mode and Redis stream target.
4. Wire direct Python publish route to pass scanner settings and publisher.
5. Add Windows live gate that enables Python scanner handoff, publishes a fixture directly to
   Python, and verifies Redis stream fields.
6. Keep route ownership unchanged.

## Acceptance Criteria

- `uv run pytest tests/test_publish_orchestration.py tests/test_publish_side_effects.py tests/test_publish_scanner_handoff.py tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q` passes.
- Windows live gate passes for direct Python publish scanner handoff.
- `git diff --name-only -- server` is empty.
- Result document records tests, live Redis stream evidence, risks, and follow-up.
