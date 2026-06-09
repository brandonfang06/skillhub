# Publish Scanner HTTP Client Result

## Summary

Completed the Python scanner HTTP client milestone.

Python scan consumer processing can now use a real HTTP scanner client instead of only a
deterministic scanner fixture. The client supports Java-compatible upload mode (`/scan-upload`)
and local mode (`/scan`), maps scanner API responses into `SecurityScanResultInput`, and preserves
the existing Redis consumer retry/ACK behavior.

## Route Ownership

No route ownership changes.

## Java Parity Checklist Outcome

- Java reference files checked:
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerAdapter.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerService.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerApiResponse.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/ScanOptions.java`
- API contract: not applicable for SkillHub HTTP routes; this is the internal scanner HTTP
  contract.
- Authorization/session behavior: not applicable.
- Database transaction atomicity: unchanged from the scan consumer runtime. Scanner HTTP failures
  still flow through Redis retry/final-failure handling.
- Audit fields: covered by reusing the scanner result application boundary.
- Storage and side effects: upload mode reads the worker-staged zip bundle and the worker cleans it
  after processing.
- Deferred parity: long-running daemon lifecycle/supervisor integration and advanced scanner auth,
  TLS, Sentinel/Cluster, or analyzer customization.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_scanner_client.py tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_config.py tests/test_hybrid_makefile.py -q
```

Result: `38 passed`.

Passed Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scanner-http-client-smoke
```

Result:

- Consumer used `scannerSource=http`.
- Consumer result: `processed=1`, `acknowledged=1`, `retried=0`, `failed=0`, `invalid=0`.
- Scanner container returned a real UUID scan id.
- Version moved from `SCANNING` to `PENDING_REVIEW`.
- Latest active `security_audit` stored scanner-generated scan id, verdict, safety flag, findings
  count, severity, and scanned timestamp.
- Redis `XPENDING` for the fixture group returned zero pending messages.
- Staged bundle directory was empty after consumer cleanup.
- Playwright smoke passed: `6 passed`.

Also verified:

```powershell
git diff --name-only -- server
```

Result: no output.

## Risks And Follow-Up

- The consumer is still invoked explicitly by fixture/gate, not as a long-running process.
- Scanner options are Java default disabled options for this milestone.
- Scanner base URL/path/timeouts are configurable, but scanner auth/TLS customization remains out
  of scope.
