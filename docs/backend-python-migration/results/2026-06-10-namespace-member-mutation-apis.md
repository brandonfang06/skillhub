# Namespace Member Mutation APIs Migration Result

Date: 2026-06-10

## Routes Changed

Python-owned:

- `POST /api/v1/namespaces/{slug}/members`
- `POST /api/web/namespaces/{slug}/members`
- `DELETE /api/v1/namespaces/{slug}/members/{userId}`
- `DELETE /api/web/namespaces/{slug}/members/{userId}`
- `PUT /api/v1/namespaces/{slug}/members/{userId}/role`
- `PUT /api/web/namespaces/{slug}/members/{userId}/role`
- `POST /api/v1/namespaces/{slug}/members/batch`
- `POST /api/web/namespaces/{slug}/members/batch`

Still Java-owned:

- `POST /api/v1/namespaces/{slug}/transfer-ownership`
- `POST /api/web/namespaces/{slug}/transfer-ownership`
- namespace profile and lifecycle mutations

## Java Parity Outcome

- `NamespaceController` member mutation routes: covered.
- `NamespacePortalCommandAppService`: covered for single-write transactions and batch partial-success behavior.
- `NamespaceMemberService`: covered for active-team checks, immutable/read-only rejection, admin-or-owner authorization, owner role protections, duplicate add, missing member, remove owner, and role update.
- Audit/storage side effects: not applicable; Java member routes do not write audit records.

## Implementation

- Extended `server-python/app/namespace/members.py` with add/remove/update/batch mutation helpers.
- Extended `server-python/app/api/namespaces.py` with v1/web member mutation routes and Java-compatible success messages.
- Added method-aware Vite ownership for member mutation routes.
- Kept transfer ownership unimplemented in Python and Java-owned in Vite.
- Added focused Python mutation tests and Vite proxy tests.
- Added `verify-namespace-member-mutation-smoke` Windows live gate.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_member_mutation.py tests/test_namespace_member_read.py tests/test_hybrid_makefile.py -q`
  - `15 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `29 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-member-mutation-smoke`
  - Python pytest: `15 passed, 1 warning`
  - Vite proxy tests: `29 passed`
  - Java/Python/Vite contract comparison checks:
    - add member matches
    - update member role matches
    - remove member matches
    - batch add matches
    - batch partial success preserved
    - direct owner assignment rejected
    - owner removal rejected
    - non-admin member operator forbidden
    - frozen namespace rejected as read-only
    - transfer ownership remains Java-owned through Vite while direct Python returns `404`
    - batch setup confirms namespace exists before per-member partial processing, matching Java's pre-loop namespace lookup
  - Playwright smoke: `6 passed`
- Post-gate status check:
  - Java backend stopped
  - Python backend stopped
  - Vite frontend stopped
  - Docker compose services removed

Repository hygiene:

- `git diff --name-only -- server`
  - no output
- `git diff --check`
  - passed; only Windows LF/CRLF warnings

## Risks And Follow-Up

- Ownership transfer remains Java-owned because it changes two membership roles and requires a separate owner-invariant plan.
- Batch add intentionally preserves Java partial success instead of wrapping the whole batch in one transaction.
- Java does not validate user existence before inserting namespace membership; Python preserves this behavior and only enriches response display/email when `user_account` exists.
