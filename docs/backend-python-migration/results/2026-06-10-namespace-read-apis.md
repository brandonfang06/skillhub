# Namespace Read APIs Result

## Summary

Moved the first namespace dashboard read group to FastAPI:

- `GET /api/v1/namespaces`
- `GET /api/web/namespaces`
- `GET /api/v1/me/namespaces`
- `GET /api/web/me/namespaces`
- `GET /api/v1/namespaces/{slug}`
- `GET /api/web/namespaces/{slug}`

Namespace create/update/delete/lifecycle/member routes remain Java-owned.

## Owner Before / After

| Route | Before | After |
| --- | --- | --- |
| `GET /api/v1/namespaces` | Java | Python |
| `GET /api/web/namespaces` | Java | Python |
| `GET /api/v1/me/namespaces` | Java | Python |
| `GET /api/web/me/namespaces` | Java | Python |
| `GET /api/v1/namespaces/{slug}` | Java | Python |
| `GET /api/web/namespaces/{slug}` | Java | Python |
| namespace mutations/member subroutes | Java | Java |

## Java Parity Outcome

- API contract: covered. Python preserves Java `ApiResponse`, `PageResponse`, `NamespaceResponse`, and `MyNamespaceResponse` field names.
- Authorization/session: covered for the local bridge. Routes require active mock user and derive namespace roles from `namespace_member`.
- Database transaction atomicity: not applicable; read-only.
- Audit/timestamp fields: not applicable; no writes.
- Storage/side effects: not applicable.
- Live verification: covered by `verify-namespace-read-smoke`.

## Behavior Covered

- `listNamespaces` returns only ACTIVE namespaces where the caller has a namespace role, sorted by slug and paginated.
- `listMyNamespaces` returns all caller memberships with lifecycle capability flags.
- `canDelete` is false when a namespace has dependent skill/review/promotion rows.
- `getNamespace` requires membership.
- Archived namespace detail is hidden from non-members with Java-compatible not-found status.
- Vite routes only the read paths to Python; namespace mutation and member routes stay Java-owned.

## Tests / Checks

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_read.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-read-smoke`
- `git diff --name-only -- server`

## Risks / Follow-Up

- Namespace member list/search and namespace mutations are still Java-owned and should be migrated as a separate milestone because they add user search, role mutation, and lifecycle/audit behavior.
- Stable live comparison intentionally ignores namespace timestamps to avoid Java/Python formatting noise; route tests still cover response field presence through unit tests.
