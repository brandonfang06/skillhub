# Promotion Approve Materialization API Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`

Already Python-owned and regression-checked:

- promotion read routes
- promotion submit routes
- promotion reject routes

Still Java-owned:

- post-publish lifecycle/governance actions

## Implementation

- Added `PromotionApproveInput` and `approve_promotion(...)` in
  `server-python/app/promotion/workflow.py`.
- Added FastAPI v1/web approval aliases in `server-python/app/api/promotions.py`.
- Updated Vite method-aware proxy rules so promotion approve routes to Python.
- Added Windows live gate action `verify-promotion-approve-smoke`.

## Java Parity Checklist Outcome

- API contract: covered. Python returns Java-compatible `PromotionResponseDto` fields in the
  SkillHub `ApiResponse` envelope.
- Authorization/session behavior: covered for local mock users. Approval requires platform
  promotion role (`SKILL_ADMIN` or `SUPER_ADMIN`) and rejects submitter self-review.
- Database transaction atomicity: covered. Approval status update, target skill/version/file
  materialization, `promotion_request.target_skill_id`, audit, and synchronous notification happen
  in one SQLAlchemy transaction.
- Audit actor/timestamp fields: covered for `PROMOTION_APPROVE`.
- Storage and side effects: covered. Python copies `skill_file` metadata rows and reuses the source
  `storage_key`, matching Java's metadata-copy behavior. No physical object-storage copy is
  performed.
- Async notification dispatcher: deferred consistently with earlier Python write milestones.
  Synchronous governance notification is covered.
- Route ownership: moved only for explicitly planned approve routes.

## Tests

Red test:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_promotion_write.py -q
```

Initial result: failed because `PromotionApproveInput` was not implemented yet.

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_promotion_write.py tests/test_promotion_read.py tests/test_hybrid_makefile.py -q
```

Result: `25 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `21 passed`.

Live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-approve-smoke
```

Final result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web promotion approve responses matched.
- Target skill rows existed in `global` with public visibility and source skill lineage.
- Target version rows were `PUBLISHED`, public, bundle/download-ready, and copied source metadata.
- Target file rows copied source file metadata and reused source storage keys.
- `promotion_request` rows were `APPROVED` and had `target_skill_id`.
- Python-owned approve audit rows existed.
- Python-owned synchronous `user_notification` rows existed.
- Unauthenticated approval returned HTTP `401`.
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Issues Found During Verification

- First live gate failed because Python approval response loading did not include
  `source_version_id` and `target_namespace_id`, which are required for materialization. The query
  was corrected and covered by the approval workflow tests.
- Second live gate failed in the verification script, not in application behavior: a SQL assertion
  used invalid `string_agg(... ORDER BY ...)` syntax. The gate SQL was corrected.
- Third live gate failed because the gate expected Postgres boolean text as `t`, while concatenated
  boolean values are `true`. The gate expectation was corrected.

## Risk / Follow-Up

- Java async notification dispatcher parity remains deferred. Direct governance notification side
  effects required by `PromotionService.approvePromotion(...)` are covered.
- Search document/event side effects from Java event listeners are not implemented in Python yet.
  They should be handled in a later post-publish lifecycle/governance/event milestone.
- Review and promotion modules should be included in the later post-migration Python module
  refactor plan.
