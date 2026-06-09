# Promotion Read Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/promotions`
- `GET /api/web/promotions`
- `GET /api/v1/promotions/pending`
- `GET /api/web/promotions/pending`
- `GET /api/v1/promotions/{id}`
- `GET /api/web/promotions/{id}`

Still Java-owned:

- `POST /api/v1/promotions`
- `POST /api/web/promotions`
- `POST /api/v1/promotions/{id}/approve`
- `POST /api/web/promotions/{id}/approve`
- `POST /api/v1/promotions/{id}/reject`
- `POST /api/web/promotions/{id}/reject`
- post-publish lifecycle/governance routes

## Implementation

- Added `server-python/app/promotion/query.py` for Java-compatible promotion read SQL.
- Added `server-python/app/api/promotions.py` for FastAPI v1/web aliases.
- List and pending routes require platform review role: `SKILL_ADMIN` or `SUPER_ADMIN`.
- Detail route allows the submitter or a platform review role, matching Java
  `ReviewPermissionChecker.canViewPromotion(...)`.
- Updated method-aware Vite proxy rules for promotion GET routes only.
- Added Windows live gate action `verify-promotion-read-smoke`.

## Java Parity Checklist Outcome

- API contract: covered with `PromotionResponseDto` and `PageResponse<PromotionResponseDto>`,
  including Java field names `sourceSkillSlug` and `sourceVersion`.
- Authorization/session behavior: covered for local mock users and platform role bindings.
- Database transaction atomicity: not applicable, read-only.
- Audit actor/timestamp fields: not applicable, no writes.
- Storage and side effects: not applicable.
- Route ownership: moved only for explicitly planned GET routes.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_promotion_read.py tests/test_hybrid_makefile.py -q
```

Result: `14 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `21 passed`.

Live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-promotion-read-smoke
```

Result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web promotion list responses matched after stable item sorting.
- Java/Python/Vite v1/Vite web pending promotion list responses matched after stable item sorting.
- Java/Python/Vite v1/Vite web promotion detail responses matched.
- Unauthenticated request returned HTTP 401.
- Promotion `POST` submit/approve/reject Vite routes remained Java-owned.
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Issue Found During Verification

The first live gate exposed a DTO field-name parity issue. Java `PromotionResponseDto` returns
`sourceSkillSlug` and `sourceVersion`, while the initial Python implementation returned
`skillSlug` and `version`. Python was corrected to use the Java field names.

The second live gate showed that list comparison must not rely on row order because Java's
`findByStatus(..., PageRequest.of(page, size))` has no explicit sort. The live gate now sorts
stable item projections before comparison.

## Risk / Follow-Up

- Promotion submit/approve/reject remain Java-owned because approval materializes a target skill
  copy and needs a separate write transaction/materialization parity plan.
- Review and promotion route modules should be included in the later post-migration Python module
  refactor plan.
