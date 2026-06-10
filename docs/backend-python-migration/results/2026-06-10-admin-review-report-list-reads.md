# Admin Review And Report List Reads Result

## Summary

Moved two admin list-read APIs to FastAPI:

- `GET /api/v1/admin/skill-reports`
- `GET /api/v1/admin/profile-reviews`

Mutation routes remain Java-owned:

- `POST /api/v1/admin/skill-reports/{reportId}/resolve`
- `POST /api/v1/admin/skill-reports/{reportId}/dismiss`
- `POST /api/v1/admin/profile-reviews/{id}/approve`
- `POST /api/v1/admin/profile-reviews/{id}/reject`

## Behavior Implemented

Skill report list:

- Requires `SKILL_ADMIN` or `SUPER_ADMIN`.
- Defaults blank status to `PENDING`.
- Trims and uppercases status.
- Rejects invalid status with Java-compatible `400`.
- Preserves Java `response.success` message (`成功`).
- Preserves `AdminSkillReportSummaryResponse` fields and nullable skill/namespace context.
- Orders reports by `created_at DESC`, matching `SkillReportJpaRepository.findByStatusOrderByCreatedAtDesc`.

Profile review list:

- Requires `USER_ADMIN` or `SUPER_ADMIN`.
- Defaults blank status to `PENDING`.
- Trims and uppercases status.
- Rejects invalid status with Java-compatible `400`.
- Preserves Java `response.success` message (`成功`).
- Sorts `PENDING` by `created_at`; non-pending statuses by `reviewed_at`.
- Preserves Java `sortDirection` fallback to `DESC`.
- Preserves `ProfileReviewSummaryResponse` fields.
- Parses `changes` and `old_values` JSONB like Java and tolerates invalid JSON as empty maps.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_admin_review_reports.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-admin-review-report-smoke`

The Windows live gate verified:

- Java direct, Python direct, and Vite proxy responses match for skill report list.
- Java direct, Python direct, and Vite proxy responses match for pending profile reviews.
- Java direct, Python direct, and Vite proxy responses match for approved profile reviews with ascending reviewed-time sort.
- Unauthorized skill report/profile review reads return `403` consistently.
- Invalid statuses return `400` consistently.
- POST mutation routes remain Java-owned through Vite fallback.
- Playwright smoke passed.

## Debug Notes

- First live gate attempt found a real envelope parity mismatch: Java uses `response.success` for these controllers, so the localized message is `成功`, not `获取成功`. Python routes were updated and tests now assert this message.
- The live gate fixture cleanup was tightened to remove prior `codex-admin-review-*` rows so failed gate attempts do not accumulate stale rows.

## Risks And Follow-Up

- Skill report resolve/dismiss and profile review approve/reject are intentionally deferred because they mutate workflow state and write audit/notification side effects.
- Admin password reset, auth/OAuth/token surfaces, skill label attach/detach, governance notification mark-read, and notification SSE remain Java-owned.
