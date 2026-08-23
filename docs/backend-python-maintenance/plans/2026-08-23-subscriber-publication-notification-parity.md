# Subscriber Publication Notification Parity Plan

Date: 2026-08-23

Status: implemented and verified; see
`docs/backend-python-maintenance/results/2026-08-23-subscriber-publication-notification-parity.md`

Branch inspected: `codex/upstream-v0.2.17-risk-first`

Baseline commit: `9f1bbdb5fc94388a4984f9f8c4cbe9479ad8a7ff`

## Objective

Make the Python backend reliably create an in-app
`SUBSCRIPTION_NEW_VERSION` notification for every eligible subscriber whenever
a subscribed skill version actually becomes `PUBLISHED`, regardless of which
supported publication workflow produced that transition.

The fix must preserve the full-Python runtime, current lifecycle rules,
notification preferences, publisher exclusion, durable notification center,
best-effort SSE delivery, replay safety, root deployment, and `/skillhub`
sub-path behavior.

## Confirmed Product Contract

Upstream `v0.2.17` uses `SkillPublishedEvent` as the shared behavior trigger
for direct auto-publish, review approval, private confirm-publish, and promotion
approval. Its notification listener sends `SUBSCRIPTION_NEW_VERSION` to the
skill's subscribers, excluding the actor who published the version.

The Python implementation should reproduce that behavior directly through
Python workflow boundaries. It must not recreate Spring events or introduce a
generic event bus merely to copy the Java structure.

The local notification contract is:

- trigger only after a version has become `PUBLISHED`;
- do not trigger for upload, `UPLOADED`, `SCANNING`, `SCAN_FAILED`,
  `PENDING_REVIEW`, `REJECTED`, withdrawal, or archive;
- notify subscribers through the existing `PUBLISH` / `IN_APP` category and
  channel, defaulting to enabled when no preference row exists;
- suppress the notification for users who disabled `PUBLISH` / `IN_APP`;
- exclude the publication actor from subscriber delivery;
- keep the existing owner-only `SKILL_PUBLISHED` behavior when the publication
  actor is also the skill owner;
- insert at most one durable row per recipient, skill, version, and event type;
- persist the notification before SSE fanout; an SSE failure must not remove
  the notification or fail an otherwise successful publication;
- include `skillId`, `versionId`, namespace, slug, display name, and version in
  the notification body so the existing UI can render and navigate correctly;
- provide in-app notification only. Email delivery is not part of the current
  platform contract.

## Current Python Gap

| Publication path | Current result | Required change |
| --- | --- | --- |
| Private `confirm-publish` in `app.lifecycle.skill` | Calls `apply_publication_outcomes`; owner/subscriber rows, replay, and SSE behavior are covered. | Preserve behavior while moving durable work into the common transaction-aware seam. |
| Public or namespace version approved in `app.review.approval` | Version becomes `PUBLISHED`; search and review-decision notification are written, but subscribers are not notified. | Add durable publication outcomes in the approval transaction and SSE after commit. This is the highest-priority user path. |
| Authorized direct auto-publish in `app.publish.orchestration` | Version starts as `PUBLISHED`; a `SkillPublishedEvent` intent is recorded but never dispatched. | Apply the common publication outcomes only when the actual prepared version status is `PUBLISHED`. |
| Promotion approval in `app.promotion.workflow` | Creates a new public target skill/version in `PUBLISHED` state without publication outcomes. | Apply the common contract for upstream parity. This normally has no pre-existing subscribers because the target skill is new. |
| Source import and re-release | Both submit through the ordinary review path (`auto_publish=False`). | No separate notification implementation; prove they inherit coverage when their review is approved. |

The existing subscription endpoints, notification API, notification-center UI,
event renderer, preferences form, and SSE transport already support the event.
The missing behavior is backend workflow wiring, not an environment-variable or
frontend/API-contract problem.

## Technical Design

### 1. Deepen the existing publication outcome module

Keep SQL and notification rules in
`server-python/app/publish/publication_outcomes.py`. Split the current helper
into two focused operations:

1. `write_publication_outcomes(connection, outcome)` validates that the exact
   version is `PUBLISHED`, locks the skill serialization point, refreshes the
   search document, resolves eligible recipients, inserts idempotent durable
   notification rows, and returns only newly inserted rows.
2. `publish_publication_notifications(notification_fanout, rows, outcome)`
   runs only after the caller's transaction commits. It attempts SSE fanout,
   logs failures, and never changes the committed publication result.

Retain a small engine-based wrapper only if existing replay or tests still need
it. New publication workflows should use the connection-scoped writer so a
published version cannot commit without its required durable notification
state. Do not add SQL to FastAPI routes.

### 2. Wire each actual `PUBLISHED` transition

- `approve_review_task`: after setting the version and skill pointer, write
  publication outcomes inside the same transaction. Continue writing the
  submitter's `REVIEW_APPROVED` notification. After commit, fan out both sets
  of newly inserted rows.
- `execute_publish_write`: write publication outcomes only when
  `prepared.version_status == "PUBLISHED"`. `PENDING_REVIEW` and private
  `UPLOADED` writes must not notify. Publish SSE after the database context
  exits successfully and independently of Redis scan-task delivery.
- `confirm_publish_skill_version`: preserve original publisher identity on
  replay and exact-once audit behavior, but use the shared connection writer
  and post-commit fanout functions.
- `approve_promotion`: use the same seam for the newly materialized target
  version, without changing existing promotion governance notifications.

Routes, response envelopes, authorization, lifecycle transitions, audit actors,
and public API shapes remain unchanged.

### 3. Preserve idempotency and concurrency

- Keep the existing recipient + event type + skill + `versionId` deduplication
  rule.
- Preserve the skill-row lock that serializes outcome creation for the same
  skill.
- A replay of the same published version may refresh search but must return no
  newly inserted notification rows and therefore produce no duplicate SSE.
- Concurrent attempts for the same transition must leave one audit mutation
  and one durable notification per eligible recipient.
- A transaction rollback must leave no publication notification and must send
  no SSE event.

No migration is expected. If concurrency testing proves the current
lock-and-`NOT EXISTS` strategy insufficient, stop and propose a separately
reviewed database uniqueness migration rather than silently changing the
schema.

## Implementation Phases And Acceptance Gates

### Phase 1: Freeze the behavior with failing tests

1. Extend focused publication-outcome tests for enabled/disabled preferences,
   publisher exclusion, owner semantics, exact body payload, replay, rollback,
   and SSE failure.
2. Add failing workflow tests proving review approval and direct auto-publish
   currently miss subscriber delivery.
3. Add negative cases proving pending review, private upload, rejection, and
   rollback do not notify.

Success criteria: new tests fail only on the missing publication-path wiring;
the existing private confirm-publish tests continue to describe the accepted
behavior.

### Phase 2: Refactor the common durable/fanout seam

1. Introduce the connection-scoped writer and post-commit publisher.
2. Keep preference filtering, subscriber lookup, publisher exclusion,
   notification payload, search refresh, and deduplication in the common
   module.
3. Adapt private confirm-publish first and run its focused fake plus real
   PostgreSQL tests before touching other workflows.

Success criteria: confirm-publish remains exact-once across replay and
concurrency; rollback leaves no search/notification state; SSE failure leaves
the durable notification visible.

### Phase 3: Cover normal review approval

1. Wire `approve_review_task` to the common writer inside its transaction.
2. Fan out publication and review-decision rows only after commit.
3. Verify the reviewer is treated as the publication actor, matching upstream:
   a reviewer subscribed to the skill is excluded, while other subscribers
   receive the version notification.
4. Verify source-imported and re-released versions inherit this behavior when
   approved.

Success criteria: a real PostgreSQL public version update produces exactly one
`SUBSCRIPTION_NEW_VERSION` row for an enabled subscriber, none for a disabled
subscriber or the reviewer, and preserves the existing `REVIEW_APPROVED`
notification and audit data.

### Phase 4: Cover auto-publish and promotion parity

1. Wire direct auto-publish only when the committed status is `PUBLISHED`.
2. Prove ordinary reviewed publish and private upload do not notify at upload
   time.
3. Wire promotion approval to the same publication contract without changing
   promotion ownership, source linkage, audit, or governance notifications.

Success criteria: real PostgreSQL tests cover direct auto-publish and promotion
materialization; rollback produces zero notification rows and zero SSE calls;
no duplicate delivery occurs on replay/concurrency.

### Phase 5: Real-service and browser acceptance

1. Start PostgreSQL, Redis, MinIO, Python scanner, Python backend, and the
   production web build together. Run Python migrations before testing.
2. Through the real UI/API, publish version `1.0.0`, approve it, subscribe as a
   user, publish version `1.1.0`, and approve it as another actor.
3. Verify the subscriber receives the live notification, the displayed skill
   and version are correct, the unread count changes, navigation reaches the
   skill detail, and the notification remains after page refresh.
4. Disable the `PUBLISH` preference and publish another version; verify no
   notification is created for that user.
5. Repeat the production-browser smoke at `/` and `/skillhub` and inspect the
   browser console plus backend logs for errors.
6. Run the complete backend suite and relevant frontend/build/deployment gates.

Success criteria: the typical reviewed public update works end to end with real
PostgreSQL and authenticated users; root and sub-path stacks have no console,
API, migration, or SQL errors; all related services are healthy throughout the
test.

## Required Tests And Commands

Run focused tests first, then the full suites. Mocks are supplementary; the
database-backed acceptance tests must use real PostgreSQL.

```powershell
cd C:\Users\USER\projects\skillhub\server-python
uv run --no-cache pytest tests/test_publish_publication_outcomes.py tests/test_skill_lifecycle_confirm_publish.py tests/test_review_approve.py tests/test_publish_orchestration.py tests/test_promotion_write.py -q

$env:SKILLHUB_TEST_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@127.0.0.1:5432/skillhub"
uv run --no-cache pytest tests/test_skill_lifecycle_confirm_publish_postgres.py tests/test_publication_notification_paths_postgres.py -q
uv run --no-cache pytest tests -q

cd C:\Users\USER\projects\skillhub\web
pnpm run typecheck
pnpm run lint
pnpm run test
corepack pnpm exec playwright test e2e/skill-subscription.spec.ts --project=chromium
pnpm run build

cd C:\Users\USER\projects\skillhub
docker compose -f docker-compose.yml config --quiet
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
docker build -t skillhub-server-python:subscriber-notification-verify -f server-python/Dockerfile .
docker build -t skillhub-web:subscriber-notification-verify -f web/Dockerfile web
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/external
git diff --check
```

For integrated acceptance, confirm these services are actually running and
healthy rather than relying on rendered configuration alone:

- `postgres`
- `redis`
- `minio`
- `skill-scanner`
- Python backend
- production web frontend

Record exact commands, service health, test counts, browser URLs, and outcomes
under `docs/backend-python-maintenance/results/` before requesting merge.

## Documentation To Update During Execution

- Extend `docs/local-python-skillhub-test-manual.zh.md` with the reviewed
  second-version subscriber-notification scenario and preference-off case.
- Update the relevant notification/subscription product guide only if it does
  not already state the final behavior accurately.
- Write a dated result under
  `docs/backend-python-maintenance/results/` containing focused, PostgreSQL,
  full-suite, production-image, root, and `/skillhub` evidence.
- Do not change `deploy/k8s/` environment-variable documentation unless
  implementation unexpectedly changes an operator contract; none is planned.

## Explicit Non-Goals

- No Java, Maven, Spring Boot, Spring events, or hybrid backend runtime.
- No email, webhook, mobile push, digest, retry queue, or new notification
  channel.
- No new environment variable or deployment topology change.
- No schema migration unless a failing real concurrency test separately proves
  one is necessary.
- No frontend redesign, notification-center redesign, generated API change, or
  new route.
- No change to subscription authorization, skill visibility, review policy,
  owner assignment, source-import ownership, or promotion governance.
- No yank/unpublish subscriber-notification work in this plan; that is a
  separate lifecycle event and should be evaluated independently.
- No unrelated notification cleanup, generic event framework, CLI change, or
  scanner protocol change.
- Do not commit, push, merge, deploy, or open a PR without later explicit user
  authorization.

## Paste-Ready Execution Prompt

```text
Execute docs/backend-python-maintenance/plans/2026-08-23-subscriber-publication-notification-parity.md in C:\Users\USER\projects\skillhub.

Follow AGENTS.md, server-python/AGENTS.md, repository skills, and current docs. Use TDD and verify each phase before continuing. Keep the full-Python FastAPI backend; do not reintroduce Java, Maven, Spring Boot, Spring events, or a hybrid runtime. Preserve unrelated worktree changes.

Implement the common publication outcome seam so durable notification/search state is written in the same transaction that makes a version PUBLISHED, while SSE fanout happens only after commit and remains best-effort. Cover normal review approval first, then direct auto-publish, preserve private confirm-publish replay/concurrency behavior, and complete promotion parity. Notify enabled subscribers with SUBSCRIPTION_NEW_VERSION, exclude the publication actor, preserve owner SKILL_PUBLISHED semantics, and never notify before PUBLISHED or more than once per recipient/skill/version/event.

Use focused tests first, then real PostgreSQL integration tests. Finally start PostgreSQL, Redis, MinIO, the Python scanner, Python backend, and production web together. Run the real reviewed second-version subscription flow in a browser at both / and /skillhub, verify live and persisted notifications, preference suppression, unread count, navigation, console, backend logs, migrations, and SQL behavior. Run the full backend/frontend/build/deployment gates and record exact evidence in docs/backend-python-maintenance/results/. Do not commit, push, merge, deploy, or open a PR without explicit authorization.
```
