# Governance Workbench Read APIs Result

Date: 2026-06-10

## Scope Completed

Moved these governance workbench read routes to Python ownership:

- `GET /api/v1/governance/summary`
- `GET /api/web/governance/summary`
- `GET /api/v1/governance/inbox`
- `GET /api/web/governance/inbox`
- `GET /api/v1/governance/activity`
- `GET /api/web/governance/activity`
- `GET /api/v1/governance/notifications`
- `GET /api/web/governance/notifications`

Kept Java-owned:

- `POST /api/v1/governance/notifications/{id}/read`
- `POST /api/web/governance/notifications/{id}/read`

## Implementation Notes

- Added `server-python/app/governance/workbench.py` for summary, inbox, activity, and legacy governance notification reads.
- Added `server-python/app/api/governance.py` and registered it in `server-python/app/main.py`.
- Updated Vite method-aware proxy rules for GET-only governance workbench reads.
- Added `verify-governance-workbench-smoke` to the Windows hybrid live gate.

## Parity Outcome

- Summary preserves Java platform/namespace-scoped pending counts and unread legacy `user_notification` count.
- Inbox preserves Java review/promotion/report item shape, namespace/platform visibility, type filtering, merged timestamp sorting, and page envelope.
- Activity preserves Java role visibility: `SKILL_ADMIN`, `SUPER_ADMIN`, and `AUDITOR` can read; other users receive an empty page.
- Governance notifications intentionally read the legacy `user_notification` table, not the newer `notification` table.
- Mark-read remains Java-owned and was checked through Vite fallback.

## Live Gate Notes

The first live gate attempt exposed a fixture SQL assumption: the current schema did not expose a matching unique constraint for `ON CONFLICT (namespace_id, slug)` on `skill`. The fixture was changed to use unique suffixes with insert-only rows.

The second attempt exposed stale `codex-governance-*` fixture rows from the failed run and volatile envelope fields in stable comparisons. The gate now:

- strips top-level `timestamp` and `requestId` before comparing Java/Python/proxy JSON
- cleans old `codex-governance-*` rows before inserting new fixtures
- compares deterministic slices: namespace-manager inbox, admin report inbox, activity `size=1`, summary, notifications, and mark-read fallback

## Verification

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_governance_workbench.py tests/test_hybrid_makefile.py -q`
  - Passed: 11 tests
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: 32 tests
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-governance-workbench-smoke`
  - Passed: Python tests, Vite proxy tests, Java/Python/proxy live contract comparison, Playwright smoke
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 status`
  - Java backend stopped
  - Python backend stopped
  - Vite frontend stopped

## Risks And Follow-Up

- Legacy governance notification mark-read remains Java-owned.
- Admin skill reports, profile review, and audit-log routes remain Java-owned.
- The live gate avoids comparing admin all-inbox first page because Java fetches first pages from source repositories before merging, and old local fixtures can make that first page non-deterministic. Unit tests cover merge behavior directly; live gate covers deterministic slices against Java.
