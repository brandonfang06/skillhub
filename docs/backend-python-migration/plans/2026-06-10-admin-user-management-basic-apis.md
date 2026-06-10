# Admin User Management Basic API Migration Plan

## Summary

Move the core admin user management APIs from Java to Python:

- `GET /api/v1/admin/users`
- `PUT /api/v1/admin/users/{userId}/role`
- `PUT /api/v1/admin/users/{userId}/status`
- `POST /api/v1/admin/users/{userId}/approve`
- `POST /api/v1/admin/users/{userId}/disable`
- `POST /api/v1/admin/users/{userId}/enable`

This milestone does not move:

- `POST /api/v1/admin/users/{userId}/password-reset`

Password reset remains Java-owned because it depends on local-auth reset token behavior.

## Java Contract

Reference files, read-only:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/UserManagementController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/AdminUserAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/repository/AdminUserSearchRepository.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminUserSummaryResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/AdminUserMutationResponse.java`
- `server/skillhub-app/src/main/resources/db/migration/V1__init_schema.sql`

Behavior to preserve:

- All migrated routes require `USER_ADMIN` or `SUPER_ADMIN`.
- List defaults to `page=0&size=20`, orders users by `created_at DESC`, supports optional
  case-insensitive `search` over `id`, `display_name`, and `email`, and optional status filter.
- List response item fields are `id`, `username`, `email`, `status`, `platformRoles`, `createdAt`.
- Users with no explicit role binding return platform role `USER`.
- Role mutation deletes existing role bindings and inserts the requested role unless role is `USER`.
- Only an actor with `SUPER_ADMIN` can assign `SUPER_ADMIN`.
- Status mutation only supports `ACTIVE` and `DISABLED`.
- `approve` and `enable` are aliases for setting `ACTIVE`; `disable` sets `DISABLED`.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/admin/users` | java | python |
| PUT | `/api/v1/admin/users/{userId}/role` | java | python |
| PUT | `/api/v1/admin/users/{userId}/status` | java | python |
| POST | `/api/v1/admin/users/{userId}/approve` | java | python |
| POST | `/api/v1/admin/users/{userId}/disable` | java | python |
| POST | `/api/v1/admin/users/{userId}/enable` | java | python |
| POST | `/api/v1/admin/users/{userId}/password-reset` | java | java |

## Implementation Scope

Allowed edits:

- `server-python/app/admin/`
- `server-python/app/api/`
- `server-python/tests/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`
- Generated frontend OpenAPI files
- Password reset route ownership
- OAuth/session/token ownership

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Preserve Java envelope messages and page/mutation response fields. |
| Authorization/session | covered | Local mock user must have `USER_ADMIN` or `SUPER_ADMIN`. |
| Database transaction atomicity | covered | Role/status mutations run in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | not applicable | Java admin user service does not write audit rows for these mutations. |
| Storage/side effects | not applicable | No object storage side effects. |
| Auth side effects | deferred | Password reset stays Java-owned. |
| Live verification | covered | Java/Python/Vite compare covers list, mutations, permissions, and password-reset proxy boundary. |

## Tests

- Python service tests:
  - list sorts by created time, filters search/status, and applies default `USER` role.
  - role mutation replaces bindings and rejects `USER_ADMIN` assigning `SUPER_ADMIN`.
  - status mutation accepts `ACTIVE`/`DISABLED` and rejects unsupported statuses.
- FastAPI route tests:
  - 401 without mock user, 403 without admin role, Java-compatible envelopes for migrated routes.
- Vite proxy tests:
  - migrated admin user routes go to Python.
  - password-reset remains Java fallback.
- Windows live gate:
  - `verify-admin-user-management-smoke`

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_admin_user_management.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-admin-user-management-smoke`
- `git diff --name-only -- server`
- `git diff --check`
