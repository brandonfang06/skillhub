# Publish Scanner Result Processing Plan

## Milestone

Add the Python foundation for applying security scanner results after publish scanner handoff.

This is a larger but still bounded milestone: Python already creates `security_audit` rows, marks
non-published versions as `SCANNING`, and publishes Redis scan task payloads. This milestone adds
the missing result-application boundary that mirrors Java `SecurityScanService.processScanResult`.

## Route Ownership

No route ownership changes.

| Method | Route | Owner Before | Owner After |
| --- | --- | --- | --- |
| all publish write routes currently Python-owned | unchanged | python | python |
| scanner stream consumer / worker route | n/a | not implemented | not implemented |

## Java Contract

When a scan result arrives:

- Find the latest active `security_audit` for `(skill_version_id, scanner_type)` ordered by
  `created_at DESC`.
- Update audit fields:
  - `scan_id`
  - `verdict`
  - `is_safe = verdict == SAFE`
  - `max_severity`
  - `findings_count`
  - `findings`
  - `scan_duration_seconds`
  - `scanned_at`
- Load the `skill_version`.
- Only if the version status is `SCANNING`, transition:
  - requested visibility `PRIVATE` -> `UPLOADED`
  - all other requested visibility values -> `PENDING_REVIEW`
- Leave `PUBLISHED`, `REJECTED`, `YANKED`, and other non-`SCANNING` statuses untouched.

## Implementation Scope

- Add `server-python/app/publish/scanner_result.py`.
- Add focused pytest coverage for result application and status transition parity.
- Add a Windows live gate that seeds DB rows, invokes the Python result processor against live
  PostgreSQL, and checks DB state.
- Update migration docs and route registry only as needed.

## Non-Goals

- No long-running Redis stream consumer.
- No scanner HTTP client implementation.
- No retry/reclaim worker behavior.
- No route ownership changes.
- No edits under `server/`.

## Verification

- `cd server-python; uv run pytest tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scanner-result-processing-smoke`
- `git diff --name-only -- server` must be empty.
