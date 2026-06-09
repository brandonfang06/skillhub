# Review Package Download Ownership Result

Date: 2026-06-09

## Routes Changed

Moved to Python:

- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`

Still Java-owned:

- promotion review routes
- post-publish lifecycle/governance routes

## Implementation

- Added `ReviewDownloadResult` and `read_review_download_package(...)` under
  `server-python/app/review/query.py`.
- Reused review visibility authorization from review detail, skill-detail, and file content.
- Download target is the review task's bound active skill version.
- Prebuilt bundle path matches Java: `packages/{skillId}/{versionId}/bundle.zip`.
- Fallback zip is built from available `skill_file` storage objects sorted by `file_path`.
- Review download does not increment public download counters.
- Attachment response mirrors Java:
  - `Content-Disposition: attachment; filename="..."`
  - storage-probed content type for prebuilt bundle
  - `application/zip` for fallback zip
  - explicit `Content-Length`
- Updated Vite method-aware proxy ownership for review download GET aliases.
- Added Windows live gate action `verify-review-download-smoke`.

## Tests

Passed:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_review_download.py tests/test_review_file_content.py tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q
```

Result: `56 passed, 1 warning`.

Passed:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result: `1 passed`, `20 passed`.

Passed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-download-smoke
```

Result:

- Python tests passed.
- Vite proxy tests passed.
- Java/Python/Vite v1/Vite web download responses matched by status, content type,
  content-disposition shape, byte length, and SHA-256.
- Unauthenticated request returned HTTP 401.
- Review download did not increment public `skill.download_count`.
- Playwright smoke passed (`6 passed`).
- Post-gate status showed Java, Python, and Vite stopped.

## Issue Found During Verification

The first live gate failed because Windows Java local storage returned
`application/x-zip-compressed` for `.zip` prebuilt bundles, while Python returned `application/zip`.
Python now probes the local mimetype for prebuilt bundle responses. Fallback zip responses remain
`application/zip`, matching Java fallback behavior.

## Risk / Follow-Up

- Promotion review APIs remain Java-owned and should be planned separately.
- Review route/query code is now large enough to include in the post-migration refactor plan.
