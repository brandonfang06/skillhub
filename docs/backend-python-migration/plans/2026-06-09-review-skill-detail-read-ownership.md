# Review Skill-Detail Read Ownership

Date: 2026-06-09

## Scope

Move only these review-bound skill detail read routes to Python:

- `GET /api/v1/reviews/{id}/skill-detail`
- `GET /api/web/reviews/{id}/skill-detail`

Keep these routes Java-owned in this milestone:

- `GET /api/v1/reviews/{id}/file`
- `GET /api/web/reviews/{id}/file`
- `GET /api/v1/reviews/{id}/download`
- `GET /api/web/reviews/{id}/download`
- promotion review routes

`server/` remains read-only and is only used as the parity reference.

## Java Contract

The Java route first authorizes review visibility with the same rule as review detail:

- the submitter can view the review;
- namespace `OWNER` / `ADMIN` can view non-global namespace review tasks;
- platform `SKILL_ADMIN` / `SUPER_ADMIN` can view review tasks;
- otherwise return `review.no_permission`.

The response is `ReviewSkillDetailResponse`:

- `skill`: review-bound `SkillDetailResponse` with `resolutionMode = "REVIEW_TASK"`;
- `versions`: all lifecycle-visible versions for the skill, sorted by Java lifecycle priority;
- `files`: available files for the active review version only;
- `documentationPath`: `README.md` first, then `SKILL.md`, otherwise null;
- `documentationContent`: UTF-8 content of the selected documentation file;
- `downloadUrl`: `/api/v1/reviews/{id}/download`;
- `activeVersion`: the review task version string.

For `versions[].downloadAvailable`, Java returns true for the active review version even when it is
not published. Other versions are downloadable only when `status = PUBLISHED` and `download_ready`
is true.

## Route Split

Vite method-aware proxy must route only the skill-detail GET aliases to Python:

- Python: `GET /api/v1/reviews/{id}/skill-detail`
- Python: `GET /api/web/reviews/{id}/skill-detail`
- Java fallback remains for review file/download aliases.

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

- Red test before implementation: `cd server-python; uv run pytest tests/test_review_skill_detail.py -q`
- Narrow Python regression:
  `cd server-python; uv run pytest tests/test_review_skill_detail.py tests/test_review_detail.py tests/test_review_list.py tests/test_review_submit.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_hybrid_makefile.py -q`
- Vite proxy test: `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-review-skill-detail-smoke`
- `git diff --name-only -- server` must be empty.

## Result File

Write `docs/backend-python-migration/results/2026-06-09-review-skill-detail-read-ownership.md`
after verification.
