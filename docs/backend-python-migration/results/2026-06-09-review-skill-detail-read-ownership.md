# Review Skill-Detail Read Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/reviews/{id}/skill-detail`
- `GET /api/web/reviews/{id}/skill-detail`

Still Java-owned:

- `GET /api/v1/reviews/{id}/file`
- `GET /api/web/reviews/{id}/file`
- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

## Implementation

- Added `read_review_skill_detail(...)` under `server-python/app/review/query.py`.
- Reused existing review visibility authorization helpers.
- Built Java-compatible review-bound skill detail response:
  - `resolutionMode = "REVIEW_TASK"`
  - active review version as `headlineVersion` and `ownerPreviewVersion`
  - first Java-sorted published version as `publishedVersion`
  - Java lifecycle version ordering
  - active version files filtered by local storage existence
  - README-first documentation selection
  - storage bytes decoded as UTF-8 to preserve Java-compatible CRLF/LF content
- Added FastAPI routes in `server-python/app/api/reviews.py`.
- Updated Vite method-aware proxy ownership for skill-detail GET aliases only.
- Added Windows live gate action `verify-review-skill-detail-smoke`.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q
```

Result: `38 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `20 passed`.

Passed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-skill-detail-smoke
```

Result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web review skill-detail stable contracts matched.
- Review file/download Vite routes remained Java-owned (`401`, non-404).
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Issue Found During Verification

The first live gate failed because Python used `Path.read_text()`, which normalized CRLF to LF,
while Java preserved storage object bytes. Python now reads bytes and decodes UTF-8, matching Java.

## Risk / Follow-Up

- Review file content and review package download are still Java-owned and should be separate
  milestones.
- Promotion review APIs remain Java-owned.
- The growing review query module is acceptable during migration but should be included in the
  post-migration refactor plan.
