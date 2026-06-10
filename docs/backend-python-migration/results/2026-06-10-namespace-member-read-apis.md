# Namespace Member Read APIs Migration Result

Date: 2026-06-10

## Routes Changed

Python-owned:

- `GET /api/v1/namespaces/{slug}/members`
- `GET /api/web/namespaces/{slug}/members`
- `GET /api/v1/namespaces/{slug}/member-candidates`
- `GET /api/web/namespaces/{slug}/member-candidates`

Still Java-owned:

- namespace lifecycle routes
- namespace profile mutations
- namespace member add/remove/update/batch mutations
- namespace ownership transfer

## Java Parity Outcome

- `NamespacePortalQueryAppService.listMembers`: covered.
- `NamespaceMemberCandidateService.searchCandidates`: covered.
- `UserAccountJpaRepository.search`: covered for ACTIVE filter and case-insensitive contains over display name, email, and id.
- `NamespaceService` membership/admin/immutable/read-only checks: covered.
- Audit/storage/transaction side effects: not applicable for read-only routes.

## Implementation

- Added `server-python/app/namespace/members.py` with native `sqlalchemy.text` queries.
- Added FastAPI v1/web namespace member read aliases.
- Added method-aware Vite GET-only route ownership for member read routes.
- Added focused Python route/service tests and Vite proxy tests.
- Added `verify-namespace-member-read-smoke` Windows live gate with Java/Python/Vite comparison.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_member_read.py tests/test_namespace_read.py tests/test_hybrid_makefile.py -q`
  - `14 passed, 1 warning`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `29 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-member-read-smoke`
  - Python pytest: `14 passed, 1 warning`
  - Vite proxy tests: `29 passed`
  - Java/Python/Vite contract comparison checks:
    - members match
    - candidates match
    - blank search matches
    - one active non-member candidate returned
    - existing member excluded
    - inactive user excluded
    - anonymous member list rejected
    - outsider member list forbidden
    - non-admin member candidate search forbidden
    - too-short search rejected
    - global namespace candidate search rejected as immutable
    - frozen namespace candidate search rejected as read-only
    - `POST /namespaces/{slug}/members` remains Java-owned through Vite
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

- Java `NamespaceMemberRepository.findByNamespaceId(..., Pageable)` does not define explicit sorting. Python uses `ORDER BY nm.id ASC` for deterministic output, and live verification uses fixture rows that compare stable contract fields.
- Namespace member mutation routes are intentionally not migrated yet. They need a separate transaction, authorization, audit, and ownership-transfer plan before route ownership moves.
