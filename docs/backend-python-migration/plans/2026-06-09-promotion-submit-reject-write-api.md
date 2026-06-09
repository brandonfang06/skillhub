# Promotion Submit And Reject Write API Migration Plan

## Milestone

Move the lower-risk promotion write routes to Python:

- `POST /api/v1/promotions`
- `POST /api/web/promotions`
- `POST /api/v1/promotions/{id}/reject`
- `POST /api/web/promotions/{id}/reject`

Keep promotion approval Java-owned:

- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`

## Why This Slice

Promotion submit creates a `promotion_request` and audit entry. Promotion reject updates a pending
request to `REJECTED`, records audit, and writes the synchronous governance notification. Neither
route materializes a target skill copy.

Promotion approve creates target skill/version/file records and updates `target_skill_id`, so it
needs its own transaction/materialization parity milestone.

## Route Ownership

Vite method-aware proxy routes only the planned POST paths to Python. Promotion approval remains a
Java fallback route.

## Java Parity Checklist

- Controller: `PromotionController`
- App service: `PromotionPortalAppService`
- Domain service: `PromotionService`
- Permission logic: `ReviewPermissionChecker`
- Read projection: `JpaGovernanceQueryRepository`
- Entity/schema: `PromotionRequest`, `promotion_request`, `audit_log`, `user_notification`

Checklist:

- API contract: covered. Python returns Java-compatible `PromotionResponseDto` in `ApiResponse`.
- Authorization/session behavior: covered for local mock users, platform roles, and source namespace
  roles.
- Database transaction atomicity: covered. Each write uses one SQLAlchemy transaction.
- Audit actor/timestamp fields: covered for `PROMOTION_SUBMIT` and `PROMOTION_REJECT`.
- Storage and side effects: not applicable for storage. Synchronous reject governance notification is
  covered. Async notification dispatcher events are deferred consistently with existing review write
  milestones.
- Live verification evidence: required through `verify-promotion-submit-reject-smoke`.

## Implementation Scope

Allowed:

- `server-python/app/api/promotions.py`
- `server-python/app/promotion/`
- `server-python/tests/test_promotion_write.py`
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

- Add Python workflow tests for submit validation, duplicate checks, audit, and reject audit/state.
- Add FastAPI route tests for Java envelope messages.
- Add Vite proxy tests proving submit/reject go to Python and approve remains Java.
- Add Windows live gate that compares Java/Python/Vite stable response and DB/audit state.

## Acceptance

- `cd server-python; uv run pytest tests/test_promotion_write.py tests/test_promotion_read.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-submit-reject-smoke`
- `git diff --name-only -- server` returns no paths.
