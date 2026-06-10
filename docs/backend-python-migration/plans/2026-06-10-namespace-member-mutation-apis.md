# Namespace Member Mutation APIs Migration Plan

Date: 2026-06-10

## Scope

Migrate namespace member mutation APIs from Java to Python:

- `POST /api/v1/namespaces/{slug}/members`
- `POST /api/web/namespaces/{slug}/members`
- `DELETE /api/v1/namespaces/{slug}/members/{userId}`
- `DELETE /api/web/namespaces/{slug}/members/{userId}`
- `PUT /api/v1/namespaces/{slug}/members/{userId}/role`
- `PUT /api/web/namespaces/{slug}/members/{userId}/role`
- `POST /api/v1/namespaces/{slug}/members/batch`
- `POST /api/web/namespaces/{slug}/members/batch`

Explicitly keep ownership transfer Java-owned:

- `POST /api/v1/namespaces/{slug}/transfer-ownership`
- `POST /api/web/namespaces/{slug}/transfer-ownership`

## Java Contract Reference

- `NamespaceController`
  - `addMember`
  - `batchAddMembers`
  - `removeMember`
  - `updateMemberRole`
- `NamespacePortalCommandAppService`
  - wraps single-member writes in transactions
  - deliberately keeps batch outside one transaction so partial success is possible
  - maps batch failures:
    - `alreadyExists` -> `ALREADY_MEMBER`
    - `owner.assignDirect` -> `INVALID_ROLE`
    - `notFound` / `not found` -> `USER_NOT_FOUND`
    - `immutable` / `readonly` -> `NAMESPACE_READONLY`
    - otherwise `UNKNOWN_ERROR`
- `NamespaceMemberService`
  - rejects immutable `GLOBAL` namespaces with `error.namespace.system.immutable`
  - rejects frozen/archived team namespaces with `error.namespace.readonly`
  - requires operator namespace `OWNER` or `ADMIN`
  - rejects direct owner assignment on add with `error.namespace.member.owner.assignDirect`
  - rejects direct owner role update with `error.namespace.member.owner.setDirect`
  - rejects duplicate member add with `error.namespace.member.alreadyExists`
  - rejects missing member remove/update with `error.namespace.member.notFound`
  - rejects removing owner with `error.namespace.member.owner.remove`

## Python Implementation

- Add focused mutation helpers under `server-python/app/namespace/members.py`.
- Extend `server-python/app/api/namespaces.py` with POST/PUT/DELETE member routes.
- Use native `sqlalchemy.text`; do not introduce ORM models.
- Use database transactions for single-member mutations.
- For batch add, execute each add in its own transaction-equivalent call and return Java-compatible partial results.
- Return Java-compatible envelopes:
  - add: `"创建成功"`
  - batch add: `"创建成功"`
  - update role: `"更新成功"`
  - remove: `"删除成功"`

## Proxy Ownership

Add method-aware Vite proxy ownership for only the member mutation routes listed in scope.
Keep transfer ownership and namespace profile/lifecycle mutations Java-owned.

## Tests

- Add/extend `server-python/tests/test_namespace_member_mutation.py`.
- Update `web/vite.config.test.ts`.
- Update `server-python/tests/test_hybrid_makefile.py` to require the Windows live gate:
  - `verify-namespace-member-mutation-smoke`
  - `Invoke-NamespaceMemberMutationTests`
  - `Invoke-NamespaceMemberMutationContractComparison`
  - `namespace-member-mutation-contract-result.json`

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_member_mutation.py tests/test_namespace_member_read.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-member-mutation-smoke`
- `git diff --name-only -- server` must be empty.
- `git diff --check`

## Boundaries

- Do not modify `server/`.
- Do not migrate namespace ownership transfer in this milestone.
- Do not change schema or generated frontend API types.
- Do not add audit behavior that Java does not have for these member routes.
