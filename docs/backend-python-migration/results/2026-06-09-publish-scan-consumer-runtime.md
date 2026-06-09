# Publish Scan Consumer Runtime Result

## Summary

Completed the Python Redis Stream consumer runtime for scan tasks.

Python can now create the scan consumer group, consume never-delivered stream messages, process
messages through the existing scan worker boundary, acknowledge success/invalid/retry/final-failure
messages, republish failed messages with incremented `retryCount` before Java's max retry count,
and reclaim pending messages for one-pass processing.

## Route Ownership

No route ownership changes.

## Java Parity Checklist Outcome

- Java reference files checked:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/AbstractStreamConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/RedissonScanTaskProducer.java`
- API contract: not applicable; no HTTP route was added or moved.
- Authorization/session behavior: not applicable; scan consumers are internal workers.
- Database transaction atomicity: covered for one-message processing. Redis ACK happens after
  success, invalid discard, retry republish, or final failure marking.
- Audit fields: covered by reusing the scanner result application boundary.
- Storage and side effects: covered for local bundle staging/cleanup through the one-task worker;
  this milestone adds Redis consumer group, ACK, retry republish, and pending reclaim behavior.
- Deferred parity: long-running daemon lifecycle/supervisor integration and real scanner HTTP
  client behavior.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q
```

Result: `22 passed`.

Passed Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-consumer-runtime-smoke
```

Result:

- Python consumed one Redis stream entry.
- Consumer result: `processed=1`, `acknowledged=1`, `retried=0`, `failed=0`, `invalid=0`.
- Redis `XPENDING` for the fixture group returned zero pending messages.
- Version moved from `SCANNING` to `PENDING_REVIEW`.
- Latest active `security_audit` stored scan id, verdict, safety flag, findings count, severity,
  and scanned timestamp.
- Staged bundle directory was empty after consumer cleanup.
- Playwright smoke passed: `6 passed`.

Also verified:

```powershell
git diff --name-only -- server
```

Result: no output.

## Risks And Follow-Up

- The consumer runtime is one-pass, not yet a long-running daemon.
- Scanner calls still use the scanner abstraction with deterministic fixture data in live
  verification.
- Redis auth, TLS, non-default DB selection, Sentinel, and Cluster support remain out of scope.
