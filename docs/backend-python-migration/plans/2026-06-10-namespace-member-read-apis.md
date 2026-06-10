# Namespace Member Read APIs Migration Plan

Date: 2026-06-10

## Scope

Migrate the namespace member read group from Java to Python:

- `GET /api/v1/namespaces/{slug}/members`
- `GET /api/web/namespaces/{slug}/members`
- `GET /api/v1/namespaces/{slug}/member-candidates`
- `GET /api/web/namespaces/{slug}/member-candidates`

Keep namespace member mutations Java-owned:

- `POST /api/v1/namespaces/{slug}/members`
- `DELETE /api/v1/namespaces/{slug}/members/{userId}`
- `PUT /api/v1/namespaces/{slug}/members/{userId}/role`
- `POST /api/v1/namespaces/{slug}/members/batch`
- `POST /api/v1/namespaces/{slug}/transfer-ownership`
- corresponding `/api/web` aliases when present

## Java Contract Reference

- `NamespacePortalQueryAppService.listMembers`
  - Requires current user to be a namespace member.
  - Returns `PageResponse<MemberResponse>`.
  - Joins `NamespaceMember` rows with `UserAccount` data when available.
- `NamespaceMemberCandidateService.searchCandidates`
  - Rejects immutable namespaces with `error.namespace.system.immutable`.
  - Requires namespace `OWNER` or `ADMIN`.
  - Rejects read-only namespaces with `error.namespace.readonly`.
  - Blank search returns an empty list.
  - Trimmed search shorter than 2 chars returns `error.namespace.member.search.tooShort`.
  - Size defaults to 10 when `size <= 0` and caps at 20.
  - Searches ACTIVE users by case-insensitive contains over `displayName`, `email`, and `id`.
  - Excludes the first 500 existing namespace members, matching Java's repository query limit.

## Python Implementation

- Add focused namespace member read service code under `server-python/app/namespace/`.
- Add FastAPI routes in `server-python/app/api/namespaces.py`.
- Use `sqlalchemy.text` native SQL only; no ORM mapping in this migration slice.
- Preserve Java response envelope via `ok("获取成功", ...)`.
- Reuse existing mock-user auth bridge and request id behavior.

## Proxy Ownership

- Add method-aware Vite proxy ownership for the four GET routes above to `localhost:8081`.
- Keep non-GET namespace member routes and all lifecycle/member mutation routes falling through to Java `localhost:8080`.

## Tests

- Add `server-python/tests/test_namespace_member_read.py`.
- Update `web/vite.config.test.ts`.
- Update `server-python/tests/test_hybrid_makefile.py` so the Windows live gate script must include:
  - Python pytest for namespace member read tests.
  - Vite proxy ownership tests.
  - live Java/Python/Vite contract comparison.
  - direct Python negative route boundary check for mutation routes.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_namespace_member_read.py tests/test_namespace_read.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-namespace-member-read-smoke`
- `git diff --name-only -- server` must be empty.
- `git diff --check`

## Boundaries

- Do not modify `server/`.
- Do not migrate namespace mutations in this milestone.
- Do not change schema or generated frontend API types.
