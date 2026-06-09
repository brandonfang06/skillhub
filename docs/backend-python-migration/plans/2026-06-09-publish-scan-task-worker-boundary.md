# Publish Scan Task Worker Boundary Plan

## Milestone

Add the Python worker boundary for a single scanner stream entry.

Python already publishes Redis scan tasks and can apply normalized scan results. This milestone
connects those pieces for one task payload:

1. parse Java-compatible Redis stream fields;
2. resolve a working skill package path from `skillPath` or `bundleKey`;
3. call a scanner abstraction;
4. apply the normalized scanner result;
5. clean up staged bundle files;
6. mark a still-`SCANNING` version as `SCAN_FAILED` when processing fails.

## Scope

Implemented:

- stream field parser and task model;
- local storage bundle staging from Java-compatible `packages/{skillId}/{versionId}/bundle.zip`;
- one-task worker service;
- failure status helper;
- tests for success, local path passthrough, bundle staging cleanup, invalid task rejection, and
  failure transition.

Not implemented:

- long-running daemon;
- Redis consumer group `XREADGROUP` loop;
- pending message reclaim;
- retry republish behavior;
- scanner HTTP client.

Those remain separate milestones because Java's `AbstractStreamConsumer` retry/reclaim behavior is
larger than the scanner result application boundary.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillSecurityScanService.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillScannerAdapter.java`
- API contract: not applicable. This milestone does not expose or take ownership of a route.
- Authorization/session behavior: not applicable. Scanner stream tasks are backend internal work.
- Database transaction atomicity: covered for the one-task boundary. The Python worker applies the
  scanner result in one database transaction and marks still-`SCANNING` versions `SCAN_FAILED` on
  processing failure. Redis acknowledgement/retry atomicity is deferred with the consumer loop.
- Audit actor/timestamp fields: covered for scan result application through the existing scanner
  result boundary. This milestone reuses that result writer.
- Storage and side effects: covered for local `skillPath` passthrough, Java-compatible `bundleKey`
  staging, and staged bundle cleanup. Scanner HTTP calls, Redis consumer group acknowledgement,
  retry, and pending reclaim remain deferred.
- Live verification evidence: required through
  `verify-publish-scan-task-worker-boundary-smoke`.

## Route Ownership

No route ownership changes.

## Verification

- `cd server-python; uv run pytest tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-task-worker-boundary-smoke`
- `git diff --name-only -- server` must be empty.
