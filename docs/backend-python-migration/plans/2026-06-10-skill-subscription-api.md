# Skill Subscription API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and
> `superpowers:verification-before-completion` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move authenticated skill subscription read/create viewer interaction APIs from Java to
FastAPI while keeping unsubscribe Java-owned until the social DELETE policy is cleaned up.

**Architecture:** Python will extend the focused social route/workflow module introduced by the
skill star milestone. The Python-owned mutation requires the local mock-user bridge, validates the
skill exists, inserts one `skill_subscription` row idempotently, and increments
`skill.subscription_count` only on the first insert. Read routes will mirror live Java behavior:
anonymous reads return `false` when Java permits the request, authenticated reads validate the skill
and check `skill_subscription`. Vite routes only v1/web subscription `GET` and `PUT` to Python.

**Tech Stack:** FastAPI, SQLAlchemy async `text`, existing local mock-user bridge, Vite
method-aware proxy, Windows hybrid live gate.

---

## Route Ownership

Move to Python:

- `GET /api/v1/skills/{skillId}/subscription`
- `GET /api/web/skills/{skillId}/subscription`
- `PUT /api/v1/skills/{skillId}/subscription`
- `PUT /api/web/skills/{skillId}/subscription`

Remain Java-owned:

- `DELETE /api/v1/skills/{skillId}/subscription`
- `DELETE /api/web/skills/{skillId}/subscription`
- Rating APIs.
- `GET /api/v1/me/subscriptions` and `GET /api/web/me/subscriptions`.
- Notification reads and SSE APIs.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillSubscriptionController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillSubscriptionService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/social/SkillSubscription.java`
- `server/skillhub-app/src/main/resources/db/migration/V40__skill_subscription.sql`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | planned | PUT returns update-success envelope with null data. GET returns read-success envelope with boolean data. |
| Authorization/session | planned | PUT requires local mock user. GET mirrors live Java behavior: anonymous requests are expected to return false because subscription has no dedicated authenticated GET policy. Live gate must confirm. |
| Idempotency | planned | Repeated subscribe is a no-op after the first state change and must not increment `subscription_count` again. |
| Skill existence validation | planned | Java validates skill existence for authenticated GET and PUT. Anonymous GET returns false before service lookup. |
| Counter parity | planned | Java increments `skill.subscription_count` only on first subscribe. Python will do the same in the same transaction. |
| Event parity | deferred | Java emits subscribe/unsubscribe events used by notification flows. Python will not add a social event bus in this milestone. |
| Vite proxy boundary | planned | Only v1/web `/{skillId}/subscription` GET/PUT routes move to Python. DELETE/rating/me-subscription routes remain Java-owned. |
| Live verification evidence | planned | Windows gate compares Java/Python/Vite PUT/GET response parity, DB `skill_subscription`, `subscription_count`, anonymous GET, idempotency, and Java-owned DELETE/rating boundaries. |

## TDD Steps

- [x] Add failing Python tests for subscription insert, idempotency, authenticated/anonymous check, missing skill, and route behavior.
- [x] Run the new tests and confirm the subscription cases fail before implementation.
- [x] Implement minimal Python subscription workflow and FastAPI routes.
- [x] Add failing Vite proxy tests for subscription GET/PUT ownership while DELETE/rating/me-subscription remain Java-owned.
- [x] Update `web/vite.config.ts` and verify Vite tests pass.
- [x] Add Windows live gate command for skill subscription.
- [x] Update route registry, migration sequence, and result document.
- [x] Run narrow Python tests, Vite proxy tests, `git diff --check`, `git diff --name-only -- server`, and the Windows live gate.
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- Authenticated `PUT` creates one `skill_subscription` row and increments `skill.subscription_count`.
- Repeated `PUT` remains successful and does not duplicate rows or increment the counter again.
- Anonymous `GET` returns Java-compatible false if live Java permits it.
- Authenticated `GET` returns true/false based on `skill_subscription`.
- Missing skill returns Java-compatible not-found behavior for authenticated read/mutation.
- `DELETE` routes are not Python-owned in this milestone. Live gate records the Java/proxy boundary.
- Vite routes v1/web subscription GET/PUT to Python and keeps DELETE/rating/me-subscription Java-owned.
- No files under `server/` are modified.
