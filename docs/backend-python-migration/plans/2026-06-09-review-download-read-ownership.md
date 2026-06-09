# Review Package Download Ownership

Date: 2026-06-09

## Scope

Move only these review-bound package download routes to Python:

- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`

Keep these routes Java-owned:

- promotion review routes
- post-publish lifecycle/governance routes

`server/` remains read-only and is only used as the parity reference.

## Java Contract

Java `ReviewController.downloadReviewVersion(...)`:

- requires authenticated local mock user context;
- authorizes with the same review visibility rule as review detail, skill-detail, and file;
- downloads the review task's bound skill version without public published-version eligibility checks;
- does not increment public skill/version download counters;
- prefers the prebuilt bundle at `packages/{skillId}/{versionId}/bundle.zip`;
- falls back to a zip built from available `skill_file` rows when the bundle is missing;
- fallback zip entries are sorted by `filePath`;
- returns raw stream response, not `ApiResponse`;
- sets `Content-Disposition: attachment; filename="{displayName-or-slug}-{version}.zip"`;
- sets `Content-Type` from storage metadata for prebuilt bundle, or `application/zip` for fallback;
- sets `Content-Length`;
- may redirect to a presigned URL only when object storage provides one. LocalFile storage returns none.

## Route Split

Vite method-aware proxy must route the review download GET aliases to Python:

- Python: `GET /api/v1/reviews/{id}/download`
- Python: `GET /api/web/reviews/{id}/download`

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

- Red test before implementation: `cd server-python; uv run pytest tests/test_review_download.py -q`
- Narrow Python regression:
  `cd server-python; uv run pytest tests/test_review_download.py tests/test_review_file_content.py tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- Vite proxy test: `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-download-smoke`
- `git diff --name-only -- server` must be empty.

## Result File

Write `docs/backend-python-migration/results/2026-06-09-review-download-read-ownership.md`
after verification.
