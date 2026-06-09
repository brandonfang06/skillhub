# Review Approve Write Ownership Plan

## Milestone

Move the review approval mutation to Python:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`

This is the first Group E lifecycle/governance mutation. It intentionally starts with approve only
because publish, scanner handoff, scanner result application, and the scan daemon are already
available in Python.

## Scope

Implemented in this milestone:

- Python review approval service that mirrors Java's `ReviewService.approveReview(...)`.
- FastAPI routes for v1 and web review approve aliases.
- Vite proxy ownership for approve POST only.
- Unit tests for transition behavior, permission behavior, route envelope, and proxy ownership.
- Windows live gate that seeds equivalent pending review fixtures, calls Java/Python/Vite, and
  compares stable response and database fields.

Not implemented:

- Review submit, reject, withdraw, list, pending list, my submissions, detail, review file, or
  review download routes.
- Promotion review APIs.
- Full notification delivery parity. The milestone records the direct audit log and core state
  transition; async notification/event processing remains deferred.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/ReviewController.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/ReviewPortalAppService.java`
  - `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewService.java`
  - `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/review/ReviewPermissionChecker.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/ReviewTaskResponse.java`
- API contract: `ApiResponse<ReviewTaskResponse>` with Java-localized success message
  `更新成功`.
- Authorization/session behavior: use the existing local mock auth bridge. Platform
  `SUPER_ADMIN` and `SKILL_ADMIN` may review; namespace `OWNER`/`ADMIN` may review non-global
  namespace tasks. Submitters cannot self-review global tasks unless `SUPER_ADMIN`.
- Database transaction atomicity: update review task, skill version, skill, and audit log in one
  DB transaction.
- Audit fields: record `REVIEW_APPROVE` on target type `REVIEW_TASK` with optional
  `{"comment":"..."}` detail.
- Storage and side effects: not applicable.
- Live verification evidence: required through `verify-review-approve-smoke`.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/reviews/{id}/approve`
- `POST /api/web/reviews/{id}/approve`

Remain Java-owned:

- `POST /api/v1/reviews`
- `POST /api/web/reviews`
- `POST /api/v1/reviews/{id}/reject`
- `POST /api/web/reviews/{id}/reject`
- `POST /api/v1/reviews/{id}/withdraw`
- `POST /api/web/reviews/{id}/withdraw`
- `GET /api/v1/reviews/**`
- `GET /api/web/reviews/**`

## Implementation Notes

- Keep `server/` read-only.
- Add `server-python/app/review/approval.py` for review approval SQL and response mapping.
- Add `server-python/app/api/reviews.py` for route bindings.
- Register the router in `server-python/app/main.py`.
- Add method-aware Vite proxy rules or explicit Vite proxy entries for approve POST only.
- Keep raw SQL strategy consistent with the current migration bridge.

## Verification

- `cd server-python; uv run pytest tests/test_review_approve.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-approve-smoke`
- `git diff --name-only -- server` must be empty.
