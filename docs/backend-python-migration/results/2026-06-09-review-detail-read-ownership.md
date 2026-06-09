# Review Detail Read Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/reviews/{id}`
- `GET /api/web/reviews/{id}`

Still Java-owned:

- `GET /api/v1/reviews/{id}/skill-detail`
- `GET /api/web/reviews/{id}/skill-detail`
- `GET /api/v1/reviews/{id}/file`
- `GET /api/web/reviews/{id}/file`
- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

## Implementation

- Added Python review detail query support in `server-python/app/review/query.py`.
- Added FastAPI detail routes with Java-compatible `ReviewTaskResponse` and `获取成功` envelope.
- Preserved Java permissions:
  - submitter can view;
  - platform `SKILL_ADMIN` / `SUPER_ADMIN` can view;
  - namespace `OWNER` / `ADMIN` can view non-global namespace reviews;
  - unrelated users receive `review.no_permission`.
- Added method-aware Vite proxy rules for one-segment review detail routes without taking over
  `skill-detail`, `file`, or `download` subroutes.
- Added Windows live gate `verify-review-detail-smoke`.

## Verification

Passed:

- `cd server-python; uv run pytest tests/test_review_detail.py -q`
- `cd server-python; uv run pytest tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-detail-smoke`

Live gate evidence:

- Java direct, Python direct, Vite `/api/v1`, and Vite `/api/web` stable detail contracts matched.
- Skill-detail, file, and download subroutes through Vite returned Java-owned boundary status `401`.
- Playwright smoke E2E passed: `6 passed`.
- Post-gate status check showed Java, Python, and Vite stopped.

## Risks And Follow-Up

- Review skill-detail remains Java-owned and should be the next Group E milestone.
- Review file/download still require storage behavior parity and should stay separate unless the
  skill-detail comparison proves they need to move together.

## Server Directory Guard

`git diff --name-only -- server` must remain empty for this milestone.
