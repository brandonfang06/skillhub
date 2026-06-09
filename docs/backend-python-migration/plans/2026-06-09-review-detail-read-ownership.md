# Review Detail Read Ownership Plan

Date: 2026-06-09

## Milestone

Move review detail read ownership to Python for:

- `GET /api/v1/reviews/{id}`
- `GET /api/web/reviews/{id}`

This milestone does not move review skill-detail, review file, review download, or promotion review
routes.

## Java Parity Contract

Java entrypoints:

- `ReviewController.getReviewDetail`
- `ReviewPortalAppService.getReviewDetail`
- `ReviewService.canViewReview`
- `JpaGovernanceQueryRepository.getReviewTaskResponse`

Expected behavior:

- Response uses Java `ApiResponse` with `msg = 获取成功`.
- Missing review task returns `review_task.not_found`.
- Missing namespace returns `namespace.not_found`.
- Submitter can view their own review task.
- A non-submitter can view when they have platform role `SKILL_ADMIN` or `SUPER_ADMIN`.
- A non-submitter can view a non-global namespace review when they have namespace role `OWNER` or
  `ADMIN`.
- A non-submitter without those permissions receives `review.no_permission`.
- Response body is Java `ReviewTaskResponse`.

## Route Ownership

Python-owned after this milestone:

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

Vite must use method-aware GET routing for the one-segment detail route only.

## Files Allowed

- `server-python/**`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

`server/**` is read-only and must not be modified.

## Tests And Verification

Narrow tests:

- `cd server-python; uv run pytest tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-detail-smoke`

The live gate must compare Java, Python direct, Vite `/api/v1`, and Vite `/api/web` detail
behavior, and verify skill-detail/file/download remain Java-owned boundaries.
