# Namespace Profile And Lifecycle API Migration Result

## Summary

Moved namespace profile and lifecycle mutation routes to Python:

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

This completes the core namespace management route group. Auth/OAuth/token/admin user/label
management and notification SSE remain Java-owned.

## Java Parity Outcome

Preserved behavior from Java namespace services:

- Create requires `SKILL_ADMIN` or `SUPER_ADMIN`.
- Create validates slug and duplicate namespace, creates a `TEAM`/`ACTIVE` namespace, and grants
  creator `OWNER`.
- Update requires namespace `OWNER` or `ADMIN`, rejects immutable or non-active namespaces, and
  updates profile fields.
- Delete requires namespace `OWNER`, rejects immutable/dependent namespaces, removes members, and
  deletes the namespace.
- Freeze/unfreeze require `OWNER` or `ADMIN` and valid source states.
- Archive/restore require `OWNER` and valid source states.
- Lifecycle mutations insert Java-compatible namespace audit log rows.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_namespace_profile_lifecycle.py tests/test_hybrid_makefile.py -q`
  - `10 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `29 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-namespace-profile-lifecycle-smoke`
  - Python/guard tests: `10 passed`
  - Vite proxy tests: `29 passed`
  - Java/Python/Vite live contract checks all `true`
  - Playwright smoke: `6 passed`

Live gate covered:

- create status/type and owner membership
- update profile shape
- delete envelope and row removal
- freeze/unfreeze/archive/restore status transitions
- freeze audit log evidence
- member update forbidden
- member archive forbidden
- create platform role required

## Debug Note

The first live gate attempt failed `memberArchiveForbidden` because the negative check reused a
namespace that had already been archived successfully. Java, Python, and Vite all returned `400`
state-transition invalid before reaching role authorization. The fixture was corrected to use fresh
active namespaces for the forbidden archive check, and the gate passed.

## Risks And Follow-up

- Auth/OAuth/API token routes remain Java-owned.
- Admin user management and label mutation routes remain Java-owned.
- Notification SSE remains Java-owned.
- Final proxy cleanup and Python schema migration ownership remain deferred until remaining endpoint
  groups are migrated and verified.
