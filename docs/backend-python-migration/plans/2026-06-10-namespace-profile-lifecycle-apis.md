# Namespace Profile And Lifecycle API Migration Plan

## Summary

Move the remaining namespace profile and lifecycle mutation routes from Java to Python:

- `POST /api/v1/namespaces`
- `POST /api/web/namespaces`
- `PUT /api/v1/namespaces/{slug}`
- `PUT /api/web/namespaces/{slug}`
- `DELETE /api/v1/namespaces/{slug}`
- `DELETE /api/web/namespaces/{slug}`
- `POST /api/v1/namespaces/{slug}/freeze`
- `POST /api/web/namespaces/{slug}/freeze`
- `POST /api/v1/namespaces/{slug}/unfreeze`
- `POST /api/web/namespaces/{slug}/unfreeze`
- `POST /api/v1/namespaces/{slug}/archive`
- `POST /api/web/namespaces/{slug}/archive`
- `POST /api/v1/namespaces/{slug}/restore`
- `POST /api/web/namespaces/{slug}/restore`

This milestone completes the core namespace management route group after namespace read/member
read/member mutation/ownership-transfer milestones.

## Java Contract

Reference files, read-only:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/NamespaceController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/NamespacePortalCommandAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/GovernanceWorkflowAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceGovernanceService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/NamespaceAccessPolicy.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/SlugValidator.java`

Behavior to preserve:

- Create requires authenticated user with platform role `SKILL_ADMIN` or `SUPER_ADMIN`.
- Create validates namespace slug, rejects duplicates, creates a `TEAM`/`ACTIVE` namespace, and
  grants creator `OWNER`.
- Update requires namespace `OWNER` or `ADMIN`, rejects immutable and non-active namespaces, and
  updates non-null profile fields.
- Delete requires namespace `OWNER`, rejects immutable namespaces, rejects namespaces with dependent
  skills/reviews/promotions, deletes namespace members, and deletes the namespace.
- Freeze/unfreeze require `OWNER` or `ADMIN` and valid source state.
- Archive/restore require `OWNER` and valid source state.
- Lifecycle mutations reject global namespaces as immutable and record Java-compatible audit logs.

## Route Ownership

| Method | Route group | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1|web/namespaces` | java | python |
| PUT | `/api/v1|web/namespaces/{slug}` | java | python |
| DELETE | `/api/v1|web/namespaces/{slug}` | java | python |
| POST | `/api/v1|web/namespaces/{slug}/freeze` | java | python |
| POST | `/api/v1|web/namespaces/{slug}/unfreeze` | java | python |
| POST | `/api/v1|web/namespaces/{slug}/archive` | java | python |
| POST | `/api/v1|web/namespaces/{slug}/restore` | java | python |

Remain Java-owned:

- `/api/v1/auth/**`
- `/oauth2/**`
- API token management
- notification SSE

## Implementation Scope

Allowed edits:

- `server-python/app/namespace/`
- `server-python/app/api/namespaces.py`
- `server-python/tests/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`
- Generated frontend OpenAPI files
- Auth/OAuth/token/SSE implementation

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Preserve Java envelopes, success messages, DTO fields, and error status classes. |
| Authorization/session | covered | Uses local mock auth bridge with platform roles and namespace memberships. |
| Database transaction atomicity | covered | Each mutation uses one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Lifecycle actions insert `audit_log` rows with actor/action/target/request context. |
| Storage/side effects | not applicable | No object storage side effects. |
| Live verification | covered | Java/Python/Vite compare covers success, role boundaries, dependency guard, and audit evidence. |

## Tests

- Python service tests:
  - create platform role and duplicate/slug validation
  - update owner/admin and readonly/permission failures
  - delete owner-only and dependency guard
  - freeze/unfreeze/archive/restore state transitions and audit log writes
- FastAPI route tests:
  - v1/web aliases, request envelope, auth, and platform role propagation
- Vite proxy tests:
  - new namespace mutation route ownership goes to Python
  - auth/OAuth/token/SSE remain Java fallback
- Windows live gate:
  - `verify-namespace-profile-lifecycle-smoke`
  - direct Java vs direct Python vs Vite proxy contract comparison

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_namespace_profile_lifecycle.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-namespace-profile-lifecycle-smoke`
- `git diff --name-only -- server`
- `git diff --check`
