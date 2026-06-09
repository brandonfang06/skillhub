# Publish Scan Task Worker Boundary Result

## Summary

Completed the Python one-task scanner worker boundary.

Python can now parse Java-compatible Redis scan task fields, resolve local `skillPath` or
`bundleKey` inputs, call a scanner abstraction, apply normalized scanner results, clean staged
bundle files, and mark still-`SCANNING` versions as `SCAN_FAILED` when worker processing fails.

## Route Ownership

No route ownership changes.

## Java Parity Checklist Outcome

- Java reference files checked:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillSecurityScanService.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillScannerAdapter.java`
- API contract: not applicable; no HTTP route was added or moved.
- Authorization/session behavior: not applicable; scan tasks are backend internal work.
- Database transaction atomicity: covered for the one-task worker. Scanner result application uses
  the existing database writer, and worker failure marks still-`SCANNING` versions `SCAN_FAILED`.
- Audit fields: covered by reusing the scanner result application boundary.
- Storage and side effects: covered for local `skillPath`, local `bundleKey` staging, and staged
  file cleanup.
- Deferred parity: long-running Redis consumer group behavior, acknowledgement, retry republish,
  pending reclaim, and scanner HTTP client behavior.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q
```

Result: `16 passed`.

Passed Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-task-worker-boundary-smoke
```

Result:

- Python parsed Redis stream fields for `skillhub:scan:requests`.
- Python staged `packages/{skillId}/{versionId}/bundle.zip`.
- Worker applied scanner result and moved the version from `SCANNING` to `PENDING_REVIEW`.
- Latest active `security_audit` stored scan id, verdict, safety flag, findings count, severity,
  and scanned timestamp.
- Staged bundle directory was empty after worker cleanup.
- Playwright smoke passed: `6 passed`.

Also verified:

```powershell
git diff --name-only -- server
```

Result: no output.

## Risks And Follow-Up

- The worker boundary is not yet a long-running daemon.
- Redis consumer group acknowledgement, retry republish, and pending reclaim remain deferred.
- Scanner HTTP client parity remains deferred; this milestone uses a scanner abstraction with a
  deterministic fixture for live verification.
