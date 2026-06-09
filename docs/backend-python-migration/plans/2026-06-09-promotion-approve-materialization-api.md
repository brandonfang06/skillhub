# Promotion Approve Materialization API Migration Plan

## Milestone

Move promotion approval to Python:

- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`

Already Python-owned and kept in scope for regression:

- promotion read routes
- promotion submit routes
- promotion reject routes

## Why This Slice Is Heavier

Promotion approval materializes a new public target skill in the target global namespace. It is not
just a status update:

- Optimistically updates `promotion_request` to `APPROVED`.
- Creates a new `skill` row in the global namespace with `source_skill_id`.
- Creates a published target `skill_version` copied from the source version.
- Updates the target skill's `latest_version_id`.
- Copies `skill_file` rows by reusing source `storage_key`.
- Updates `promotion_request.target_skill_id`.
- Writes `PROMOTION_APPROVE` audit.
- Writes the synchronous governance `user_notification`.

Because Java reuses file storage keys and only copies metadata rows, Python can keep approval in one
database transaction without adding object-storage side effects.

## Route Ownership

Move only approval POST aliases to Python:

- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`

No new unrelated routes are moved in this milestone.

## Java Parity Checklist

References:

- Controller: `PromotionController`
- App service: `PromotionPortalAppService.approvePromotion(...)`
- Domain service: `PromotionService.approvePromotion(...)`
- Permission logic: `ReviewPermissionChecker.canReviewPromotion(...)`
- Read projection: `JpaGovernanceQueryRepository.getPromotionResponse(...)`
- Entities/schema: `promotion_request`, `skill`, `skill_version`, `skill_file`, `audit_log`,
  `user_notification`

Checklist:

- API contract: covered. Return Java-compatible `PromotionResponseDto` in `ApiResponse`.
- Authorization/session behavior: covered for local `X-Mock-User-Id`; platform role
  `SKILL_ADMIN`/`SUPER_ADMIN` required and submitter self-review forbidden.
- Database transaction atomicity: covered. Approval state update, materialized skill/version/file
  rows, target skill id update, audit, and synchronous notification must happen in one SQLAlchemy
  transaction.
- Audit actor/timestamp fields: covered for `PROMOTION_APPROVE`.
- Storage and side effects: covered for metadata-only `skill_file.storage_key` reuse. No physical
  storage copy is performed because Java does not copy package objects here.
- Async notification dispatcher: deferred consistently with earlier review/promotion write
  milestones. Synchronous governance notification is covered.
- Live verification evidence: required through `verify-promotion-approve-smoke`.

## Implementation Scope

Allowed:

- `server-python/app/api/promotions.py`
- `server-python/app/promotion/workflow.py`
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

- Add Python workflow tests for approval materialization:
  - status update before materialization
  - target skill insert
  - target version insert
  - `latest_version_id` update
  - file row copy with reused storage keys
  - `promotion_request.target_skill_id` update
  - `PROMOTION_APPROVE` audit
  - synchronous `user_notification`
- Add negative tests for non-pending, self-review/no platform permission, and duplicate target skill.
- Add FastAPI route test for approve envelope and request forwarding.
- Add Vite proxy tests proving approve goes to Python.
- Add Windows live gate that compares Java/Python/Vite v1/Vite web stable responses and DB state.

## Acceptance

- `cd server-python; uv run pytest tests/test_promotion_write.py tests/test_promotion_read.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-approve-smoke`
- `git diff --name-only -- server` returns no paths.
