# Publish Scanner Result Processing Result

## Summary

Added the Python foundation for applying scanner results to publish-created versions.

This milestone does not add a long-running Redis consumer. It adds and verifies the database
result-application boundary that the future consumer will call.

## Route Ownership

No route ownership changed.

## Implemented

- Added `server-python/app/publish/scanner_result.py`.
- Added `apply_security_scan_result(...)`, matching Java `SecurityScanService.processScanResult`:
  - selects the latest active `security_audit` by `(skill_version_id, scanner_type)`;
  - updates `scan_id`, `verdict`, `is_safe`, `max_severity`, `findings_count`, `findings`,
    `scan_duration_seconds`, and `scanned_at`;
  - transitions `SCANNING` + `PUBLIC` or `NAMESPACE_ONLY` to `PENDING_REVIEW`;
  - transitions `SCANNING` + `PRIVATE` to `UPLOADED`;
  - leaves non-`SCANNING` statuses untouched.
- Added `server-python/scripts/apply_scan_result_fixture.py` for Windows live DB verification.
- Added `verify-publish-scanner-result-processing-smoke` to the hybrid Windows gate.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q
```

Result: `10 passed`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scanner-result-processing-smoke
```

Result:

- Python/server tests: `10 passed`.
- Live DB fixture:
  - public `SCANNING` version moved to `PENDING_REVIEW`;
  - private `SCANNING` version moved to `UPLOADED`;
  - audit rows updated with scan id, verdict, safety flag, findings count, max severity,
    findings JSON, and scanned timestamp;
  - Python apply return values matched DB state.
- Playwright smoke: `6 passed`.

Port cleanup was checked after the live gate; no listeners remained on `3000`, `8080`, `8081`, or
`8000`.

## Risks

- Redis stream consumer, retry/reclaim behavior, and scanner HTTP client calls are still deferred.
- This result processor assumes the scanner payload has already been normalized into the internal
  `SecurityScanResultInput` shape.

## Follow-Up

- Add Python Redis scan task consumer or equivalent worker boundary.
- Add scanner HTTP client adapter if Python should call the scanner directly instead of consuming
  normalized results from a worker.
