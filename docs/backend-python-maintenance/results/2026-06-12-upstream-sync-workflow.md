# Upstream Sync Workflow Result

Date: 2026-06-12

Milestone: Post Python Cutover Hardening Milestone 7

## Scope

This milestone added a repeatable workflow for tracking future open-source upstream changes after the Python backend cutover.

## Remote State

| Remote | URL | Notes |
| --- | --- | --- |
| `origin` | `https://github.com/brandonfang06/skillhub.git` | Working fork; current hardening branch is pushed here. |
| `snapshot-fork` | `https://github.com/brandonfang06/skillhub-fork.git` | Snapshot/archive fork. |
| `upstream` | `https://github.com/iflytek/skillhub.git` | Canonical open-source upstream; push URL is disabled. |

Refs after `git fetch upstream --prune`:

- `upstream/main`: `47765503915f0f9eaaff5ef65a50f08a1ccc34f5`
- hardening branch head: final drift report was rerun after this milestone commit.

## Changes

- Added `scripts/check-upstream-backend-drift.ps1`.
- Added `docs/backend-python-maintenance/upstream-sync-workflow.md`.
- Updated `docs/backend-python-maintenance/README.md` with the upstream drift command.
- Updated `server-python/AGENTS.md` so future Python backend hardening work checks upstream drift before milestone batches.
- Updated `docs/backend-python-maintenance/post-python-cutover-hardening-plan.md` to mark Milestone 7 complete.

## Drift Report Summary

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef HEAD
```

Result summary:

- `java-backend-contract-or-behavior`: 0
- `database-migration-or-schema`: 0
- `frontend-or-api-client-expectation`: 12
- `python-backend-runtime`: 247
- `docs-config-or-ci`: 287
- `scanner-cli-or-other-runtime`: 4

Interpretation: current drift is dominated by local Python cutover/hardening and documentation work. There is no current upstream Java backend or Flyway schema category item in `upstream/main...HEAD` that requires an immediate Python port.

## Workflow Rules Added

- Fetch and run the drift report before each hardening milestone batch and at least weekly while pre-launch.
- Use triage decisions: `port-to-python-now`, `accept-non-backend`, `defer-with-reason`, or `reject`.
- Port Java behavior changes by adding or updating Python tests first.
- Convert upstream Java Flyway migrations into Python-owned schema migration work before launch.
- Treat security, auth, token scope, session, lifecycle, publish, review, promotion, and data-integrity changes as high-impact until inspected.

## Verification

- `git fetch upstream --prune`
  - Result: success
- `powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef HEAD`
  - Result: success; report generated with the summary above
- `git diff --check`
  - Result: no whitespace errors; PowerShell reported only CRLF working-copy warnings.

## Residual Risk

- The drift script categorizes by path. Humans still need to inspect file content before making final triage decisions.
- `upstream/main...HEAD` includes all local Python cutover work because upstream does not contain `server-python`. For future intake windows, pass a narrower base/head pair when comparing a specific upstream batch.
