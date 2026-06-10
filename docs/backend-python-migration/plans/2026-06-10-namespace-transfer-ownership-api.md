# Namespace Transfer Ownership API Migration Plan

## Summary

Move namespace ownership transfer from Java to Python for both v1 and web aliases:

- `POST /api/v1/namespaces/{slug}/transfer-ownership`
- `POST /api/web/namespaces/{slug}/transfer-ownership`

This milestone follows the namespace member mutation migration. It does not move namespace
create/update/delete/freeze/unfreeze/archive/restore APIs.

## Java Contract

Reference files, read-only:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NamespaceController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/NamespacePortalCommandAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceMemberService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceAccessPolicy.java`

Behavior to preserve:

- Request body: `{ "newOwnerId": "<user id>" }`.
- Auth actor is the current owner from `X-Mock-User-Id` during local migration.
- Namespace must allow `canTransferOwnership`: `TEAM` and `ACTIVE`.
- Non-transferable namespace returns `error.namespace.readonly`.
- Current actor membership must exist, otherwise `error.namespace.owner.current.notFound`.
- Current actor role must be `OWNER`, otherwise `error.namespace.owner.current.invalid`.
- New owner membership must exist, otherwise `error.namespace.owner.new.notFound`.
- Success changes current owner role to `ADMIN` and new owner role to `OWNER`.
- Success response data is `{ "message": "Ownership transferred successfully" }` with updated envelope.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/namespaces/{slug}/transfer-ownership` | java | python |
| POST | `/api/web/namespaces/{slug}/transfer-ownership` | java | python |

Remain Java-owned:

- `POST /api/v1/namespaces`
- `PUT /api/v1/namespaces/{slug}`
- `DELETE /api/v1/namespaces/{slug}`
- `POST /api/v1/namespaces/{slug}/freeze`
- `POST /api/v1/namespaces/{slug}/unfreeze`
- `POST /api/v1/namespaces/{slug}/archive`
- `POST /api/v1/namespaces/{slug}/restore`
- web aliases for the same lifecycle/profile APIs

## Implementation Scope

Allowed edits:

- `server-python/app/namespace/members.py`
- `server-python/app/api/namespaces.py`
- `server-python/tests/test_namespace_member_mutation.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`
- Generated frontend schema files
- New unrelated namespace lifecycle APIs

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Body shape, response envelope, and success message mirror Java controller/service. |
| Authorization/session | covered | Local migration uses `X-Mock-User-Id` and requires authenticated user. |
| Database transaction atomicity | covered | Role swap must happen inside one SQLAlchemy `engine.begin()` transaction. |
| Audit actor/timestamp fields | not applicable | Java transfer service only updates member roles through repository; no audit log observed. |
| Storage/side effects | not applicable | No file/storage side effect. |
| Live verification | covered | Java/Python/Vite compare must include successful role swap and negative errors. |

## Tests

- Python unit/service tests:
  - success role swap
  - current owner missing
  - current actor not owner
  - new owner missing
  - frozen/global namespace returns `error.namespace.readonly`
- FastAPI route test:
  - v1/web aliases return Java-compatible envelope
  - missing auth returns 401
- Vite proxy tests:
  - transfer ownership POST routes go to Python
  - other namespace lifecycle/profile mutation routes remain Java fallback
- Windows live gate:
  - `verify-namespace-transfer-ownership-smoke`
  - direct Java, direct Python, and Vite proxy response/DB role-state comparison

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_namespace_member_mutation.py tests/test_hybrid_makefile.py`
- `cd web; npx vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-namespace-transfer-ownership-smoke`
- `git diff --name-only -- server`
- `git diff --check`
