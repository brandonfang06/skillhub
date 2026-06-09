# Review Submit Write Ownership Plan

Date: 2026-06-09

## Milestone

Move review submission write ownership to Python for:

- `POST /api/v1/reviews`
- `POST /api/web/reviews`

This milestone does not move review list/detail reads, promotion review, or any
other review route.

## Java Parity Contract

Java entrypoint:

- `ReviewController.submitReview`
- `ReviewPortalAppService.submitReview`
- `ReviewService.submitReview`

Expected behavior:

- Body contract is `{ "skillVersionId": <number> }`.
- Caller identity comes from `X-Mock-User-Id` in local development.
- Load `skill_version`, `skill`, and `namespace`; missing rows keep Java error
  keys: `skill_version.not_found`, `skill.not_found`, `namespace.not_found`.
- Reject frozen/archived namespaces with `error.namespace.frozen` /
  `error.namespace.archived`.
- Caller may submit when they are the skill owner, have platform role
  `SKILL_ADMIN` or `SUPER_ADMIN`, or have namespace role `OWNER` or `ADMIN`.
- Only `DRAFT` and `UPLOADED` versions may be submitted; otherwise return
  `review.submit.not_draft`.
- Duplicate pending review task for the same version returns
  `review.submit.duplicate`.
- On success, within one DB transaction:
  - set `skill_version.status = PENDING_REVIEW`;
  - insert a `review_task` with status `PENDING`, version `1`, submitter, and
    timestamp;
  - write `REVIEW_SUBMIT` audit for target type `REVIEW_TASK` with
    `{"skillVersionId": <id>}`;
  - return Java-shaped `ReviewTaskResponse` in `ApiResponse` with message
    `创建成功`.

## Route Ownership

Python-owned after this milestone:

- `POST /api/v1/reviews`
- `POST /api/web/reviews`

Still Java-owned:

- `GET /api/v1/reviews`
- `GET /api/web/reviews`
- `GET /api/v1/reviews/{id}`
- `GET /api/web/reviews/{id}`
- promotion review routes

Vite must use method-aware exact path routing so POST submit goes to Python
while GET review reads continue to Java.

## Files Allowed

- `server-python/**`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

`server/**` is read-only and must not be modified.

## Tests And Verification

Narrow tests:

- `cd server-python; uv run pytest tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`

Windows live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-submit-smoke`

The live gate must compare Java, Python direct, Vite `/api/v1`, and Vite
`/api/web` submit behavior, including response shape, DB status/task changes,
audit log, and route ownership boundaries for Java-owned review reads.
