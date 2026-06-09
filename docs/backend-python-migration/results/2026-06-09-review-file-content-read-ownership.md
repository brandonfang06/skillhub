# Review File Content Read Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/reviews/{id}/file?path=...`
- `GET /api/web/reviews/{id}/file?path=...`

Still Java-owned:

- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

## Implementation

- Added `read_review_file_content(...)` under `server-python/app/review/query.py`.
- Reused review visibility authorization from review detail and skill-detail.
- Read only files from the review task's bound active skill version.
- Filtered files through storage object existence before reading, matching Java `availableFiles(...)`.
- Returned raw bytes with `application/octet-stream`; no `ApiResponse` envelope.
- Preserved Java path validation:
  - blank path rejected;
  - any `..` rejected;
  - leading `/` rejected.
- Updated Vite method-aware proxy ownership for review file GET aliases only.
- Added Windows live gate action `verify-review-file-smoke`.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_review_file_content.py tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q
```

Result: `49 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `20 passed`.

Passed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-file-smoke
```

Result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web raw file responses matched by status, content type, length, and SHA-256.
- Invalid path returned HTTP 400 when mock-user auth was present.
- Review download Vite route remained Java-owned (`401`, non-404).
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Risk / Follow-Up

- Review package download is still Java-owned and should be the next Group E milestone.
- Promotion review APIs remain Java-owned.
- Review route/query code is growing and should be included in the post-migration refactor plan.
