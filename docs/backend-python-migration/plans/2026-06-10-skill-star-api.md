# Skill Star API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move skill star/check viewer interaction APIs from Java to FastAPI.

**Architecture:** Python will add a focused social route/workflow module for star state. The
Python-owned mutation requires the local mock-user bridge, remains idempotent, validates the skill
exists, mutates `skill_star`, and refreshes `skill.star_count`. Read routes require the local
mock-user bridge in live Java security behavior and check `skill_star` for authenticated callers.
Vite will route only the v1/web star `GET` and `PUT` routes to Python.

**Tech Stack:** FastAPI, SQLAlchemy async `text`, existing auth mock-user bridge, Vite method-aware
proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `PUT /api/v1/skills/{skillId}/star`
- `GET /api/v1/skills/{skillId}/star`
- `PUT /api/web/skills/{skillId}/star`
- `GET /api/web/skills/{skillId}/star`

Remain Java-owned:

- `DELETE /api/v1/skills/{skillId}/star`.
- `DELETE /api/web/skills/{skillId}/star`.
- Rating APIs.
- Subscription APIs.
- `GET /api/v1/me/stars` and `GET /api/web/me/stars`.
- Notification and governance inbox APIs.

Live Java finding: `DELETE /api/v1/skills/{skillId}/star` is currently caught by the broader
`DELETE /api/v1/skills/*/*` route-security policy and returns 403 for a normal local mock user.
`DELETE /api/web/skills/{skillId}/star` remains Java-owned through the Vite fallback. This milestone
does not move either DELETE route; unstar should be handled later with the broader social/security
route policy cleanup.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillStarController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillStarService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/listener/SkillStarEventListener.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | PUT returns update-success envelope with null data. GET returns read-success envelope with boolean data. |
| Authorization/session | planned | PUT/GET require a local mock user in live Java behavior. The Java controller has a null-principal false branch, but current security rejects anonymous calls before it is reached. DELETE remains Java-owned/deferred because live Java v1 returns 403 for a normal user. |
| Idempotency | planned | Repeated star is a no-op after the first state change. Python keeps an unstar service helper covered by tests, but no DELETE route ownership moves in this milestone. |
| Skill existence validation | planned | Java validates skill existence for star and authenticated GET. Anonymous GET is rejected by current security before controller execution. |
| Counter parity | planned | Java refreshes `skill.star_count` through a transactional event listener. Python will refresh synchronously inside the same transaction for deterministic live verification. |
| Event parity | deferred | Java emits star/unstar events. Python has no event bus equivalent yet; record as broader social/notification follow-up. |
| Vite proxy boundary | planned | Only v1/web `/{skillId}/star` GET/PUT routes move to Python. DELETE, rating, subscription, and me-star routes remain Java-owned. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite PUT/GET response parity, DB `skill_star`, `star_count`, authenticated GET, unauthenticated GET rejection, idempotency, Java-owned DELETE boundary, and missing-skill behavior. |

## TDD Steps

- [x] Add failing Python tests for star, authenticated/anonymous check, idempotency, and route behavior.
- [x] Run the new tests and confirm behavior was covered before/with implementation.
- [x] Implement minimal Python social star workflow and FastAPI routes.
- [x] Add failing Vite proxy tests for star route ownership while DELETE/rating/subscription remain Java-owned.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for skill star.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Authenticated `PUT` creates one `skill_star` row and refreshes `skill.star_count`.
- Repeated `PUT` remains successful and does not duplicate rows.
- `DELETE` routes are not Python-owned in this milestone. Live gate records that Java v1 DELETE is
  blocked for a normal mock user and that Vite DELETE remains Java-owned.
- Anonymous `GET` is rejected with the same status as live Java security behavior.
- Authenticated `GET` returns true/false based on `skill_star`.
- Missing skill returns Java-compatible not-found behavior for authenticated read/mutations.
- Vite routes v1/web star GET/PUT to Python and keeps DELETE/rating/subscription Java-owned.
- No files under `server/` are modified.
