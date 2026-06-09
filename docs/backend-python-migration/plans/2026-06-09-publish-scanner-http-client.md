# Publish Scanner HTTP Client Plan

## Milestone

Add the Python scanner HTTP client used by the scan consumer runtime.

The publish scanner chain currently reaches a scanner abstraction with deterministic fixture data.
This milestone replaces that fixture in the live gate with a real HTTP client that calls the
scanner service, while keeping daemon lifecycle and route ownership unchanged.

## Scope

Implemented:

- Java-compatible scanner API response mapping:
  - `is_safe=true` -> `SAFE`
  - `is_safe=false`, `max_severity=CRITICAL` -> `BLOCKED`
  - `is_safe=false`, `max_severity=HIGH` -> `DANGEROUS`
  - `is_safe=false`, `max_severity=MEDIUM` or missing/other -> `SUSPICIOUS`
- upload-mode `POST /scan-upload` multipart client for staged zip bundles;
- local-mode `POST /scan` JSON client for directory paths;
- scanner option query/body fields matching Java's `ScanOptions.disabled()`;
- settings for scanner base URL, paths, and timeout values;
- live gate that consumes a Redis scan task and calls the real scanner container.

Not implemented:

- long-running consumer daemon;
- scanner retries beyond Redis consumer retry handling;
- scanner auth, TLS customization, or non-default analyzer options;
- changes to HTTP route ownership.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerAdapter.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerService.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/SkillScannerApiResponse.java`
  - `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/scanner/ScanOptions.java`
- API contract: not applicable for SkillHub HTTP routes. This is an internal scanner client
  contract.
- Authorization/session behavior: not applicable.
- Database transaction atomicity: unchanged from consumer runtime. Scanner failures still flow
  through the consumer retry/final-failure path.
- Audit actor/timestamp fields: scanner result application remains unchanged.
- Storage and side effects: upload mode reads the staged bundle path produced by the worker
  boundary. The worker still cleans staged files after processing.
- Live verification evidence: required through
  `verify-publish-scanner-http-client-smoke`.

## Route Ownership

No route ownership changes.

## Verification

- `cd server-python; uv run pytest tests/test_publish_scanner_client.py tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_config.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scanner-http-client-smoke`
- `git diff --name-only -- server` must be empty.
