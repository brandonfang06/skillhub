# Promotion Read API Migration Plan

## Milestone

Move promotion read routes from Java to Python:

- `GET /api/v1/promotions`
- `GET /api/web/promotions`
- `GET /api/v1/promotions/pending`
- `GET /api/web/promotions/pending`
- `GET /api/v1/promotions/{id}`
- `GET /api/web/promotions/{id}`

Write routes stay Java-owned in this milestone:

- `POST /api/v1/promotions`
- `POST /api/web/promotions`
- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`
- `POST /api/v1/promotions/{id}/reject`
- `POST /api/web/promotions/{id}/reject`

## Route Ownership

Vite will use method-aware GET-only routing for promotion read paths. POST promotion submission,
approval, and rejection continue to fall through to Java on `localhost:8080`.

## Java Parity Checklist

- Controller: `PromotionController`
- App service: `PromotionPortalAppService`
- Query repository: `JpaGovernanceQueryRepository`
- Domain permission: `ReviewPermissionChecker`
- Entity/schema: `PromotionRequest`, `promotion_request`

Checklist:

- API contract: covered. Python returns Java-compatible `PromotionResponseDto` and
  `PageResponse<PromotionResponseDto>` envelopes.
- Authorization/session behavior: covered for local mock users. List and pending require
  platform review role (`SKILL_ADMIN` or `SUPER_ADMIN`). Detail allows submitter or platform
  review role.
- Database transaction atomicity: not applicable. Read-only milestone.
- Audit actor/timestamp fields: not applicable. No writes or audit records.
- Storage and side effects: not applicable. No storage access.
- Live verification evidence: required through `verify-promotion-read-smoke`.

## Implementation Scope

Allowed:

- `server-python/app/api/promotions.py`
- `server-python/app/promotion/`
- `server-python/tests/test_promotion_read.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`
- Frontend React business code
- Generated OpenAPI files

## Tests

- Add Python repository and FastAPI route tests for list, pending, detail, and permission failures.
- Add Vite proxy tests proving GET promotion routes go to Python and POST promotion routes remain Java.
- Add Windows live gate that compares Java/Python/Vite stable response contracts.

## Acceptance

- `cd server-python; uv run pytest tests/test_promotion_read.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-read-smoke`
- `git diff --name-only -- server` returns no paths.
