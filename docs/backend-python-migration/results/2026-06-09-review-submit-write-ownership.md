# Review Submit Write Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `POST /api/v1/reviews`
- `POST /api/web/reviews`

Still Java-owned:

- `GET /api/v1/reviews`
- `GET /api/web/reviews`
- `GET /api/v1/reviews/{id}`
- `GET /api/web/reviews/{id}`
- promotion review routes

## Implementation

- Added FastAPI review submit routes with Java-compatible request body
  `{ "skillVersionId": number }`.
- Added Python review submit service logic:
  - loads version, skill, namespace, and submitter display name;
  - enforces active namespace status;
  - allows skill owner, platform `SKILL_ADMIN` / `SUPER_ADMIN`, or namespace `OWNER` / `ADMIN`;
  - allows only `DRAFT` and `UPLOADED`;
  - moves the version to `PENDING_REVIEW`;
  - creates a pending `review_task`;
  - writes `REVIEW_SUBMIT` audit with `skillVersionId`;
  - returns Java-shaped `ReviewTaskResponse`.
- Added method-aware Vite proxy rules for exact `POST /api/v1/reviews` and
  `POST /api/web/reviews` without taking over GET review reads.
- Added Windows live gate `verify-review-submit-smoke`.

## Verification

Passed:

- `cd server-python; uv run pytest tests/test_review_submit.py -q`
- `cd server-python; uv run pytest tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-submit-smoke`

Live gate evidence:

- Java direct, Python direct, Vite `/api/v1`, and Vite `/api/web` stable response contracts matched.
- DB state matched: `PENDING|PENDING_REVIEW|<submitter>`.
- Python audit recorded `REVIEW_SUBMIT|REVIEW_TASK|<taskId>|<submitter>|{"skillVersionId": ...}`.
- GET review list/detail through Vite returned Java-owned boundary status `401`.
- Playwright smoke E2E passed: `6 passed`.
- Post-gate status check showed Java, Python, and Vite stopped.

## Risks And Follow-Up

- Review list/detail reads remain Java-owned; migrate them next if Group E continues.
- This milestone tests the owner-submit path live. Namespace admin/platform role submit paths are
  covered by service logic and should be included in read/write role matrix tests when review reads
  move.
- The Codex sandbox could not access Docker Desktop through the normal pipe/config in this run, so
  the live gate was rerun with approved elevated execution. The project docs still prefer normal
  PowerShell once the local Docker session is accessible to the sandbox.

## Server Directory Guard

`git diff --name-only -- server` must remain empty for this milestone.
