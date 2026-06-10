# Admin Audit Log Read API Result

## Summary

Moved `GET /api/v1/admin/audit-logs` to FastAPI.

The route is GET-only and now Python-owned through the Vite method-aware proxy. Audit writes remain owned by their source workflow routes.

## Route Ownership

Moved to Python:

- `GET /api/v1/admin/audit-logs`

Still Java-owned:

- `POST /api/v1/admin/users/{userId}/password-reset`
- Admin skill reports/profile reviews
- Governance notification mark-read
- Auth/OAuth/token surfaces
- Notification SSE

## Behavior Implemented

- Requires `AUDITOR` or `SUPER_ADMIN`.
- Preserves Java query parameters: `page`, `size`, `userId`, `action`, `requestId`, `ipAddress`, `resourceType`, `resourceId`, `startTime`, `endTime`.
- Preserves Java offset/page behavior: offset clamps negative pages, response returns the original page.
- Preserves Java dynamic filters, including `CAST(target_id AS TEXT)` for `resourceId`.
- Converts `startTime` and `endTime` to timezone-aware Python `datetime` values before binding to asyncpg.
- Preserves Java projection fields: `id`, `action`, `userId`, `username`, `details`, `ipAddress`, `requestId`, `resourceType`, `resourceId`, `timestamp`.
- Preserves Java `details` fallback: `detail_json` text when present, otherwise `targetType:targetId`.
- Preserves Java UTC instant timestamp text.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_audit_logs.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-audit-log-smoke`

The Windows live gate verified:

- Java direct list response equals Python direct list response.
- Python direct list response equals Vite proxy response.
- Filtered Java/Python/proxy responses match.
- Non-auditor requests return `403` on Java, Python, and proxy.
- Playwright smoke for the hybrid stack passed.

## Debug Notes

- First live gate attempt failed because the SQL fixture passed a JSON literal through PowerShell and `psql -c`; shell quoting stripped JSON double quotes before PostgreSQL saw the value. The fixture now uses `NULL` `detail_json` rows and validates fallback details deterministically. Unit tests still cover `detail_json` projection.
- Second live gate attempt found a real Python parity bug: `startTime` and `endTime` were passed to asyncpg as strings. The route/service now parse them into timezone-aware `datetime` values, matching Java `OffsetDateTime` binding semantics.

## Risks And Follow-Up

- This route reads audit logs only; audit write parity remains owned by each migrated workflow.
- Future admin report/profile review milestones should reuse the same method-aware proxy and live contract comparison pattern.
