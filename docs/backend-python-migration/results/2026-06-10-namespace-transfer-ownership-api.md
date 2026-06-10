# Namespace Transfer Ownership API Migration Result

## Summary

Moved namespace ownership transfer to Python:

- `POST /api/v1/namespaces/{slug}/transfer-ownership`
- `POST /api/web/namespaces/{slug}/transfer-ownership`

Namespace create/update/delete/freeze/unfreeze/archive/restore routes remain Java-owned.

## Ownership

| Route | Before | After |
| --- | --- | --- |
| `POST /api/v1/namespaces/{slug}/transfer-ownership` | java | python |
| `POST /api/web/namespaces/{slug}/transfer-ownership` | java | python |

## Java Parity Outcome

Preserved behavior from `NamespaceController`, `NamespacePortalCommandAppService`,
`NamespaceMemberService`, and `NamespaceAccessPolicy`:

- Request body uses `newOwnerId`.
- Current actor is the current owner.
- Namespace must be transferable: `TEAM` and `ACTIVE`.
- Non-transferable namespace returns `error.namespace.readonly`.
- Missing current owner membership returns `error.namespace.owner.current.notFound`.
- Current member with non-owner role returns `error.namespace.owner.current.invalid`.
- Missing new owner membership returns `error.namespace.owner.new.notFound`.
- Success swaps roles: current owner becomes `ADMIN`, new owner becomes `OWNER`.
- Success data remains `{ "message": "Ownership transferred successfully" }`.

No storage, audit-log, scanner, notification, or external side effects were added.

## Tests

Passed:

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_namespace_member_mutation.py tests/test_hybrid_makefile.py -q`
  - `15 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `29 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-namespace-transfer-ownership-smoke`
  - Python/guard tests: `15 passed`
  - Vite proxy tests: `29 passed`
  - Java/Python/Vite live contract checks all `true`
  - Playwright smoke: `6 passed`

Live contract checks covered:

- success envelope equality
- DB role-state equality after Java, Python, and Vite proxy calls
- existing user without namespace membership rejected as current owner missing
- non-owner current member rejected
- missing new owner rejected
- frozen namespace rejected

## Debug Note

The first live gate attempt failed `currentMissingRejected` because the test used a completely
unknown actor id. Java rejected that at the auth filter with `401`, before reaching the domain
membership check. The fixture was corrected to create an active user who is not a namespace member,
which exercises the intended Java domain behavior and returns `400` on Java, Python, and Vite.

## Risks And Follow-up

- Namespace lifecycle/profile mutation APIs still route to Java and should be migrated in a later
  namespace lifecycle milestone.
- Notification SSE and auth/session/OAuth/token surfaces remain Java-owned.
- Final proxy cleanup remains deferred until the remaining namespace/admin/auth groups are migrated.
