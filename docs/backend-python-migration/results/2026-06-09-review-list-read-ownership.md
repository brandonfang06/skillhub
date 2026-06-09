# Review List Read Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/reviews`
- `GET /api/web/reviews`
- `GET /api/v1/reviews/pending`
- `GET /api/web/reviews/pending`
- `GET /api/v1/reviews/my-submissions`
- `GET /api/web/reviews/my-submissions`

Still Java-owned:

- `GET /api/v1/reviews/{id}`
- `GET /api/web/reviews/{id}`
- `GET /api/v1/reviews/{id}/skill-detail`
- `GET /api/web/reviews/{id}/skill-detail`
- `GET /api/v1/reviews/{id}/file`
- `GET /api/web/reviews/{id}/file`
- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

## Implementation

- Added `server-python/app/review/query.py` for review read-model queries.
- Added FastAPI routes for global/namespace review list, namespace pending list, and current-user
  pending submissions.
- Preserved Java `ApiResponse` message `获取成功` and `PageResponse` shape:
  `items`, `total`, `page`, `size`.
- Implemented Java-compatible permission checks for global queue, namespace queue, pending queue,
  and current user's submissions.
- Added method-aware Vite proxy rules for exact GET list routes without taking over detail,
  skill-detail, file, or download routes.
- Added Windows live gate `verify-review-list-smoke`.

## Verification

Passed:

- `cd server-python; uv run pytest tests/test_review_list.py -q`
- `cd server-python; uv run pytest tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-list-smoke`

Live gate evidence:

- Java direct, Python direct, Vite `/api/v1`, and Vite `/api/web` stable page contracts matched for
  global review list, namespace pending list, and my-submissions list.
- Detail and skill-detail review routes through Vite returned Java-owned boundary status `401`.
- Playwright smoke E2E passed: `6 passed`.
- Post-gate status check showed Java, Python, and Vite stopped.

## Risks And Follow-Up

- Review detail remains Java-owned and should be the next Group E milestone.
- Review skill-detail, review file, and review download have additional storage/read-model behavior
  and should stay separate from plain list reads.
- The live global list can include rows from prior migration gates; the comparison intentionally
  validates Java/Python/Vite parity on the same seeded database rather than fixed totals.

## Server Directory Guard

`git diff --name-only -- server` must remain empty for this milestone.
