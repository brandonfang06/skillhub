# Review Reject/Withdraw Write Ownership Plan

## Milestone

Move review reject and withdraw mutations to Python:

- `POST /api/v1/reviews/{id}/reject`
- `POST /api/web/reviews/{id}/reject`
- `POST /api/v1/reviews/{id}/withdraw`
- `POST /api/web/reviews/{id}/withdraw`

This extends Group E after review approve ownership. Reject shares the reviewer permission and
review-task transition boundary with approve. Withdraw is included because it is the paired
submitter-side lifecycle escape hatch for pending review tasks, but it keeps a separate submitter
authorization path.

## Scope

Implemented in this milestone:

- Python reject service that mirrors Java `ReviewService.rejectReview(...)`.
- Python withdraw service that mirrors Java `ReviewPortalAppService.withdrawReview(...)` plus
  `ReviewService.withdrawReview(...)` and `SkillGovernanceService.withdrawPendingVersion(...)`.
- FastAPI routes for v1 and web reject/withdraw aliases.
- Vite proxy ownership for reject/withdraw POST only.
- Unit tests for reject transition, withdraw transition/delete behavior, route envelopes, and
  proxy ownership.
- Windows live gate that seeds equivalent pending review fixtures, calls Java/Python/Vite, and
  compares stable response, database, and audit fields.

Not implemented:

- Review submit, list, pending list, my submissions, detail, review file, or review download routes.
- Promotion review APIs.
- Full async notification/event delivery parity. This milestone records audit and core state
  parity only.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/ReviewController.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/ReviewPortalAppService.java`
  - `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewService.java`
  - `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewPermissionChecker.java`
  - `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillGovernanceService.java`
- Reject API contract: `ApiResponse<ReviewTaskResponse>` with Java-localized success message
  `更新成功`.
- Withdraw API contract: `ApiResponse<Void>` with Java-localized success message `更新成功` and
  `data: null`.
- Reject authorization: platform `SUPER_ADMIN`/`SKILL_ADMIN`, non-global namespace `OWNER`/`ADMIN`,
  and Java-compatible self-review allowance for namespace OWNER/ADMIN or `SUPER_ADMIN`.
- Withdraw authorization: only the original review submitter may withdraw.
- Reject transaction: pending review task moves to `REJECTED`, reviewer/comment/reviewed_at are
  recorded, version moves to `REJECTED`, and `REVIEW_REJECT` audit is inserted.
- Withdraw transaction: pending review task is deleted, version moves from `PENDING_REVIEW` to
  `UPLOADED`, skill `updated_by` is set to the withdrawing user, and `REVIEW_WITHDRAW` audit is
  inserted with `{"skillVersionId":...}`.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/reviews/{id}/reject`
- `POST /api/web/reviews/{id}/reject`
- `POST /api/v1/reviews/{id}/withdraw`
- `POST /api/web/reviews/{id}/withdraw`

Already Python-owned:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`

Remain Java-owned:

- `POST /api/v1/reviews`
- `POST /api/web/reviews`
- `GET /api/v1/reviews/**`
- `GET /api/web/reviews/**`
- review file/download routes
- promotion review routes

## Verification

- `cd server-python; uv run pytest tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-reject-withdraw-smoke`
- `git diff --name-only -- server` must be empty.
