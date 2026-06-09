# Skill Rating API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move authenticated skill rating read/update viewer interaction APIs from Java to FastAPI.

**Architecture:** Python will extend the social route/workflow module with rating state. The
Python-owned mutation requires the local mock-user bridge, validates the skill exists, validates
`score` is 1..5, creates or updates one `skill_rating` row, and refreshes `skill.rating_avg` /
`skill.rating_count` synchronously for deterministic parity. Read routes require the local
mock-user bridge in live Java route security and return the Java `{score, rated}` payload shape.

**Tech Stack:** FastAPI, Pydantic request model, SQLAlchemy async `text`, existing local mock-user
bridge, Vite method-aware proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `GET /api/v1/skills/{skillId}/rating`
- `GET /api/web/skills/{skillId}/rating`
- `PUT /api/v1/skills/{skillId}/rating`
- `PUT /api/web/skills/{skillId}/rating`

Remain Java-owned:

- Star DELETE and subscription DELETE until the social DELETE route-security cleanup.
- `GET /api/v1/me/stars`, `GET /api/web/me/stars`.
- `GET /api/v1/me/subscriptions`, `GET /api/web/me/subscriptions`.
- Notification reads and SSE APIs.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillRatingController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillRatingService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillRating.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillRatingRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SkillRatingStatusResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/listener/SkillRatingEventListener.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/projection/SkillEngagementProjectionService.java`
- `server/skillhub-app/src/main/resources/db/migration/V3__phase3_review_social_tables.sql`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | PUT accepts JSON body `{ "score": number }` and returns update-success envelope with null data. GET returns read-success envelope with `{ score, rated }`. |
| Authorization/session | planned | GET has explicit authenticated Java route policy; PUT falls through to authenticated default. Python requires a local mock user for both. |
| Validation | planned | Score must be 1..5. Missing/invalid score should be rejected before DB mutation. |
| Skill existence validation | planned | Java validates skill existence before score range. Python must preserve this order for authenticated mutation/read. |
| Aggregate parity | planned | Java refreshes `rating_avg` and `rating_count` through an async transactional event listener. Python will refresh synchronously after create/update for live determinism. |
| Event parity | deferred | Python will not add a social event bus in this milestone. |
| Vite proxy boundary | planned | Only v1/web `/{skillId}/rating` GET/PUT routes move to Python. Star/subscription DELETE and me-social lists remain Java-owned. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite GET/PUT response parity, DB `skill_rating`, aggregate fields, anonymous GET rejection, invalid score, and non-owned route boundaries. |

## TDD Steps

- [x] Add failing Python tests for rating create, update, invalid score, authenticated/anonymous read, missing skill, and route behavior.
- [x] Run the new tests and confirm the rating cases fail before implementation.
- [x] Implement minimal Python rating workflow and FastAPI routes.
- [x] Add failing Vite proxy tests for rating GET/PUT ownership while me-social lists remain Java-owned.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for skill rating.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Authenticated `PUT` with score 1..5 creates a `skill_rating` row.
- Repeated `PUT` by the same user updates the row instead of duplicating it.
- Aggregates match Java: `rating_count = 1`; average changes from the first score to the updated score.
- Invalid score is rejected and does not mutate the DB.
- Anonymous `GET` is rejected with the same status as live Java security behavior.
- Authenticated `GET` returns `{ score: 0, rated: false }` before rating and `{ score, rated: true }` after rating.
- Missing skill returns Java-compatible not-found behavior for authenticated read/mutation.
- Vite routes v1/web rating GET/PUT to Python and keeps me-social lists Java-owned.
- No files under `server/` are modified.
