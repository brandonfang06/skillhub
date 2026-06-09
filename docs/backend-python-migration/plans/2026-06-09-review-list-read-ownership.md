# Review List Read Ownership Plan

Date: 2026-06-09

## Milestone

Move review list read ownership to Python for:

- `GET /api/v1/reviews`
- `GET /api/web/reviews`
- `GET /api/v1/reviews/pending`
- `GET /api/web/reviews/pending`
- `GET /api/v1/reviews/my-submissions`
- `GET /api/web/reviews/my-submissions`

This milestone does not move review detail, review skill-detail, review file/download, or
promotion review routes.

## Java Parity Contract

Java entrypoints:

- `ReviewController.listReviews`
- `ReviewController.listPendingReviews`
- `ReviewController.listMySubmissions`
- `ReviewPortalAppService.listReviews`
- `ReviewPortalAppService.listPendingReviews`
- `ReviewPortalAppService.listMyReviewSubmissions`

Expected behavior:

- All responses use Java `ApiResponse` with `msg = 获取成功`.
- Page data shape is Java `PageResponse`: `items`, `total`, `page`, `size`.
- `GET /reviews` requires query `status`; status is uppercased before matching
  `ReviewTaskStatus`.
- `GET /reviews` with no `namespaceId` is the global queue and requires platform role
  `SKILL_ADMIN` or `SUPER_ADMIN`.
- `GET /reviews?namespaceId=...` checks namespace existence and allows platform review roles or
  namespace `OWNER` / `ADMIN`; otherwise `review.no_permission`.
- Sort order for `GET /reviews` uses `submittedAt` for `PENDING`, otherwise `reviewedAt`, with
  `id` as secondary sort. `sortDirection` defaults to `DESC` and invalid values fall back to
  `DESC`.
- `GET /reviews/pending` requires `namespaceId` and uses `PENDING`.
- `GET /reviews/my-submissions` returns the current user's pending submitted reviews.
- Each item is Java `ReviewTaskResponse`.

## Route Ownership

Python-owned after this milestone:

- exact GET list routes above.

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

Vite must use method-aware GET routing for these exact list aliases so detail routes stay Java-owned.

## Files Allowed

- `server-python/**`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

`server/**` is read-only and must not be modified.

## Tests And Verification

Narrow tests:

- `cd server-python; uv run pytest tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-list-smoke`

The live gate must compare Java, Python direct, Vite `/api/v1`, and Vite `/api/web` list behavior,
including response shape, pagination fields, route ownership boundaries, and Playwright smoke E2E.
