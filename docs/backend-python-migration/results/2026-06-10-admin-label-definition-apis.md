# Admin Label Definition API Migration Result

## Summary

Moved admin label definition management to FastAPI:

- `GET /api/v1/admin/labels`
- `POST /api/v1/admin/labels`
- `PUT /api/v1/admin/labels/{slug}`
- `DELETE /api/v1/admin/labels/{slug}`
- `PUT /api/v1/admin/labels/sort-order`

Skill label attach/detach routes remain Java-owned.

## Changes

- Added Python admin label service logic under `server-python/app/admin/labels.py`.
- Added FastAPI routes under `server-python/app/api/admin_labels.py`.
- Registered the router in `server-python/app/main.py`.
- Added Python unit/route tests in `server-python/tests/test_admin_label_definitions.py`.
- Added Vite method-aware proxy rules and tests for admin label definition ownership.
- Added Windows live gate `verify-admin-label-definition-smoke`.
- Updated route registry and migration sequence plan.

## Java Parity Notes

- `SUPER_ADMIN` authorization is required for all migrated routes.
- Create/update/delete/sort each run in a transaction.
- Slug normalization, translation normalization, duplicate translation checks, and max-definition checks match Java domain behavior.
- Audit actions are written as `LABEL_CREATE`, `LABEL_UPDATE`, `LABEL_DELETE`, and `LABEL_SORT_ORDER_UPDATE`.
- Live verification found one parity issue before completion: Python originally returned sort-order responses sorted by `sort_order`, but Java returns the `findByIdIn(...)->saveAll(...)` result order. Python was changed to return stable label id order, and tests were updated.

Deferred:

- Java schedules search rebuilds for skills affected by label update/delete. This remains deferred because the service is pre-launch and skill label attach/detach routes remain Java-owned.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_label_definitions.py tests/test_hybrid_makefile.py -q`
  - Result: `10 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `30 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-label-definition-smoke`
  - Result: passed
  - Live comparison covered create, update, sort-order, delete, list proxy behavior, forbidden non-admin access, DB persistence, and audit rows.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 status`
  - Result: Java backend stopped, Python backend stopped, Vite frontend stopped.

- `git diff --name-only -- server`
  - Result: no paths
- `git diff --check`
  - Result: passed; Windows line-ending warnings only

## Risks And Follow-Up

- Label update/delete search rebuild side effect is not implemented in Python yet. Revisit before production cutover or before skill label attach/detach ownership moves.
- Admin user management remains Java-owned.
- Auth/OAuth/token surfaces remain Java-owned.
