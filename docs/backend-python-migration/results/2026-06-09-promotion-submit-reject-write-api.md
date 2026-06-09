# Promotion Submit And Reject Write API Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `POST /api/v1/promotions`
- `POST /api/web/promotions`
- `POST /api/v1/promotions/{id}/reject`
- `POST /api/web/promotions/{id}/reject`

Still Java-owned:

- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`
- post-publish lifecycle/governance actions

## Implementation

- Added `server-python/app/promotion/workflow.py` for promotion submit/reject write orchestration.
- Added FastAPI v1/web submit and reject aliases in `server-python/app/api/promotions.py`.
- Updated Vite method-aware proxy rules so promotion submit/reject route to Python while approval
  falls back to Java.
- Added Windows live gate action `verify-promotion-submit-reject-smoke`.

## Java Parity Checklist Outcome

- API contract: covered. Python returns Java-compatible `PromotionResponseDto` fields in the
  SkillHub `ApiResponse` envelope.
- Authorization/session behavior: covered for local mock users. Submit allows owner, platform
  promotion role, or source namespace `OWNER`/`ADMIN`; reject requires platform promotion role and
  rejects submitter self-review.
- Database transaction atomicity: covered. Each submit/reject operation uses a single SQLAlchemy
  transaction for request state and side effects.
- Audit actor/timestamp fields: covered for `PROMOTION_SUBMIT` and `PROMOTION_REJECT`.
- Storage and side effects: storage is not applicable. Reject writes the synchronous
  `user_notification` governance notification. Java async event dispatcher behavior remains
  deferred consistently with earlier Python review write milestones.
- Route ownership: moved only for explicitly planned submit/reject routes. Promotion approve
  remains Java-owned.

## Tests

Red test:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_promotion_write.py -q
```

Initial result: failed with missing `app.promotion.workflow`, confirming the test targeted the new
workflow implementation.

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_promotion_write.py tests/test_promotion_read.py tests/test_hybrid_makefile.py -q
```

Result: `22 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `21 passed`.

Live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-submit-reject-smoke
```

Result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web submit responses matched.
- Java/Python/Vite v1/Vite web reject responses matched.
- Submit DB state matched expected `PENDING` records.
- Reject DB state matched expected `REJECTED` records with reviewer/comment.
- Python-owned submit/reject audit rows existed.
- Python-owned reject synchronous `user_notification` rows existed.
- Promotion approve proxy path remained Java-owned (`401` unauthenticated boundary).
- Unauthenticated submit/reject returned HTTP `401`.
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Risk / Follow-Up

- Promotion approval remains Java-owned because it materializes target global skill/version/file
  records and should be migrated as a separate milestone.
- Java async notification dispatcher parity is still deferred for Python write routes. Direct
  governance notification side effects required by `PromotionService.rejectPromotion(...)` are
  covered.
- Review and promotion modules should be included in the later post-migration Python module
  refactor plan.
