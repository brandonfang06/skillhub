# Publish Scan Daemon Supervisor Result

## Summary

Completed the Python scan daemon/supervisor milestone.

FastAPI can now optionally start a background scan consumer daemon through
`SKILLHUB_SCAN_CONSUMER_ENABLED=true`. The daemon is wired into app lifespan startup/shutdown,
ensures its Redis consumer group exists before polling, consumes/reclaims scan tasks through the
existing scan consumer runtime, calls the real scanner HTTP client, updates scanner audit/version
state, ACKs completed messages, and shuts down with the hybrid stack.

## Route Ownership

No route ownership changes.

## Java Parity Checklist Outcome

- Java reference files checked:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/AbstractStreamConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
- API contract: not applicable. This milestone does not expose or move an HTTP route.
- Authorization/session behavior: not applicable.
- Database transaction atomicity: unchanged from the scan consumer runtime. Each daemon iteration
  opens a DB transaction for consume/reclaim processing.
- Audit fields: covered by reusing the scanner result application boundary.
- Storage and side effects: covered by reusing the worker boundary; staged bundles are cleaned
  after daemon processing.
- Deferred parity: external process supervision, multi-worker scaling policy, Redis TLS/cluster,
  and scanner auth/custom analyzer options.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_scan_daemon.py tests/test_publish_scanner_client.py tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_config.py tests/test_hybrid_makefile.py -q
```

Result: `45 passed`.

Passed Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-daemon-supervisor-smoke
```

Result:

- Daemon enabled with a unique Redis stream/group.
- Version moved from `SCANNING` to `PENDING_REVIEW`.
- Latest active `security_audit` stored scanner-generated scan id, verdict, safety flag, findings
  count, severity, and scanned timestamp.
- Redis `XPENDING` for the daemon group returned zero pending messages.
- Staged bundle directory was empty after daemon processing.
- Playwright smoke passed: `6 passed`.

Also verified:

```powershell
git diff --name-only -- server
```

Result: no output.

## Live Gate Fix

The first live gate attempts failed with Redis `NOGROUP`. Root cause was the gate script deleting
the unique daemon stream after FastAPI startup. Redis deletes consumer groups with the stream, so
the daemon-created group was gone before the test task was added.

The gate now keeps the unique stream created by the daemon. The daemon also explicitly calls
`ensure_group()` before each consume/reclaim iteration so startup is deterministic even when the
stream is initially empty.

## Risks And Follow-Up

- The daemon currently runs inside FastAPI. A separate worker process/supervisor can be planned
  later if deployment needs process isolation or multiple scan workers.
- Redis connection handling remains the existing lightweight RESP client; TLS/cluster support is
  deferred.
- Next migration milestones can build on the scanner pipeline being runnable without manual fixture
  invocation.
