# Scan Timeout Terminal-State Recovery

Date: 2026-08-11

## Problem

When the scanner's LiteLLM analysis times out, an already-open SkillHub page can
continue displaying `SCANNING`. The backend has bounded retry and
`SCAN_FAILED` handling, but the frontend skill queries do not refresh while a
scan is active.

## Scope

1. Add state-dependent polling for skill and review queries that expose a
   `SCANNING` version.
2. Refresh security-audit data while its scan is incomplete, and stop polling
   after either a completed audit or `SCAN_FAILED` version state.
3. Characterize the timeout path through the production scanner client and scan
   consumer, then verify the terminal database state with real PostgreSQL and
   Redis.
4. Add a backend stale-scan recovery mechanism only if the real-service test
   proves the existing bounded retry path can leave `SCANNING` behind.

## Success Criteria

- An open UI observes `SCANNING` changing to `SCAN_FAILED` or the successful
  post-scan state without a manual refresh.
- Polling stops in every terminal state.
- A scanner timeout cannot leave a version in `SCANNING` after retries are
  exhausted.
- Existing root and `/skillhub` behavior remains unchanged.

## Non-Goals

- Changing the Cisco scanner's LLM prompt or model configuration.
- Retrying failed scans from the browser.
- Treating a timeout as a successful or safe scan.

## Result

- The affected frontend queries poll every three seconds only while a visible
  skill version is `SCANNING`. They stop after `SCAN_FAILED` or any successful
  post-scan state.
- Security-audit queries refresh while their audit is incomplete and stop when
  the audit completes or the version reaches `SCAN_FAILED`.
- No backend watchdog was added. The production scan daemon already runs each
  consumer iteration inside `engine.begin()`, and a real Redis/PostgreSQL test
  proved that a LiteLLM-style `httpx.ReadTimeout` on the final retry commits
  `SCAN_FAILED` and acknowledges the stream message.
- The default retry policy remains unchanged: the UI continues to show
  `SCANNING` while backend retries are legitimately in progress, then updates
  without a manual refresh.

## Verification

- Frontend focused tests: 6 files, 17 tests passed.
- Frontend full suite: 210 files, 834 tests passed.
- Frontend ESLint, TypeScript build, and Vite production build passed.
- `/skillhub` Playwright suite: 20 desktop/mobile Chromium scenarios passed.
- Backend consumer/daemon focused suite: 16 tests passed.
- Backend real-service timeout integration: 1 test passed against PostgreSQL 16
  and Redis 7.
- Backend full suite with real PostgreSQL and Redis enabled: 1271 tests passed.
- Targeted Ruff for the new integration test passed. The repository-wide Ruff
  command reports 425 pre-existing findings outside this change.
- The test Redis stream and PostgreSQL fixture were both absent after cleanup.
