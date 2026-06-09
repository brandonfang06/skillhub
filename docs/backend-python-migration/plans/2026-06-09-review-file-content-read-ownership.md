# Review File Content Read Ownership

Date: 2026-06-09

## Scope

Move only these review-bound single-file content routes to Python:

- `GET /api/v1/reviews/{id}/file?path=...`
- `GET /api/web/reviews/{id}/file?path=...`

Keep these routes Java-owned:

- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

`server/` remains read-only and is only used as the parity reference.

## Java Contract

Java `ReviewController.getReviewFile(...)`:

- requires `path` query param;
- rejects `null`, blank, paths containing `..`, and paths starting with `/` with HTTP 400;
- authorizes with the same review visibility rule as review detail and review skill-detail;
- reads the file from the review task's bound skill version only;
- filters through `availableFiles(...)`, meaning the file must have a storage object;
- returns raw bytes with `Content-Type: application/octet-stream`;
- does not wrap success in `ApiResponse`.

## Route Split

Vite method-aware proxy must route only the review file GET aliases to Python:

- Python: `GET /api/v1/reviews/{id}/file?path=...`
- Python: `GET /api/web/reviews/{id}/file?path=...`
- Java: `GET /api/*/reviews/{id}/download`

## Implementation Boundaries

Allowed edits:

- `server-python/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/`

Forbidden edits:

- `server/**`

## Verification

- Red test before implementation: `cd server-python; uv run pytest tests/test_review_file_content.py -q`
- Narrow Python regression:
  `cd server-python; uv run pytest tests/test_review_file_content.py tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- Vite proxy test: `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-file-smoke`
- `git diff --name-only -- server` must be empty.

## Result File

Write `docs/backend-python-migration/results/2026-06-09-review-file-content-read-ownership.md`
after verification.
