# Backend Python Migration Sequence Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:writing-plans` when changing this
> sequence, and use `superpowers:executing-plans` when implementing an approved milestone. This is
> the living migration order document; update this file whenever priorities change.

**Goal:** Maintain the agreed migration order for moving SkillHub backend APIs from Java to
FastAPI before the service goes live for the organization.

**Architecture:** Java under `server/` remains read-only throughout migration and is used as a
contract/reference runtime. Python-owned routes live under `server-python/` and are routed by Vite
dev proxy during migration. Because this is pre-launch, future milestones should prefer cohesive
API areas or complete workflows over long-term fine-grained Java/Python coexistence.

**Tech Stack:** Spring Boot Java backend as read-only reference, FastAPI Python backend on port
`8081`, Vite dev proxy on port `3000`, Java backend on port `8080`, PostgreSQL through
SQLAlchemy async engine after no-DB routes are stable.

---

## How To Use This Plan

This file is the source of truth for migration order. For every milestone:

1. Announce the selected API, API group, or workflow before changing files.
2. Create or update a milestone-specific plan under
   `docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md`.
3. Complete the Java parity checklist gate before code changes.
4. Implement with TDD.
5. Update `docs/backend-python-migration/route-registry.md` when ownership changes.
6. Write a result document under `docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md`.
7. Run unit/proxy verification.
8. Run the live verification gate before starting the next migration group.
9. Confirm `git diff --name-only -- server` returns no paths.
10. Commit and push to `dev`.

If priorities change, update this file first, then continue from the revised order.

## Java Parity Checklist Gate

Every milestone plan must include a Java parity checklist section based on:

- `docs/backend-python-migration/java-parity-checklist.md`

The plan section must identify the Java controller/service/repository/domain reference files or
state why the milestone has no Java behavioral owner. It must classify API contract,
authorization/session behavior, database transaction atomicity, audit actor/timestamp fields,
storage and side effects, and live verification evidence as `covered`, `not applicable`, or
`deferred`.

Every result document must record the checklist outcome, including accepted reviewer feedback,
deferred parity gaps, tests added for accepted fixes, and whether any unresolved gap blocks route
ownership.

Do not move route ownership when parity gaps are unresolved for the route being moved. Foundation
helper milestones may defer route-level parity only when the affected route remains Java-owned and
the Windows live gate proves the route still reaches Java through Vite.

## Live Verification Gate

Every migration milestone must pass a live verification gate before the next group starts. This
gate is required even when unit tests and Vite proxy tests pass.

Windows procedure:

- `docs/backend-python-migration/windows-live-verification.md`

Minimum gate for routes migrated from Java:

- Start the hybrid stack for the target platform.
- Call the Java reference route directly when it still exists on Java.
- Call the Python-owned route directly.
- Compare the stable contract fields; ignore volatile fields such as `timestamp` and `requestId`.
- Call the Vite proxy route and confirm it reaches the Python-owned implementation.
- Run frontend smoke E2E when the route affects frontend flows.
- Record pass/fail/blocker details in a result document.
- Do not begin the next migration group until this gate has passed or the project owner explicitly
  accepts a recorded blocker.

## Non-Negotiable Boundaries

- Do not modify any file under `server/`.
- Do not edit Java config, migrations, controllers, services, tests, generated DTOs, or resources.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not migrate auth, session, OAuth, CSRF, API token, idempotency, publish, lifecycle mutation,
  storage download, or admin mutation APIs until their bridge designs are explicitly planned.
- Pre-launch milestones may own a larger API group when the group has a written route matrix,
  tests, and live verification. Avoid unnecessary proxy fragmentation.

## Python Data Access Strategy

The Java backend uses JPA/domain services/repositories. During migration, the Python backend uses
SQLAlchemy async engine with explicit SQL (`sqlalchemy.text`) for migrated catalog, file metadata,
file content, and download read paths. This is intentional bridge code for Java contract parity and
low blast radius; it is not an accidental rejection of ORM.

Current rules:

- Keep SQL inside narrow repository/helper functions instead of route handlers.
- Do not introduce SQLAlchemy ORM models for catalog/read/download migrations unless a milestone
  explicitly plans that refactor.
- Prefer explicit SQL while route behavior is still being compared against Java field-by-field.
- Cover every query behavior with Python tests and live Java/Python/Vite verification before
  moving to the next group.
- Revisit repository and ORM boundaries before publish/upload/lifecycle mutations, because those
  require stronger transaction, authorization, idempotency, and domain modeling.

## Selection Criteria

Prefer earlier groups when they are:

- Public or anonymous-readable.
- Internally cohesive as a workflow or API area.
- Easy to compare against Java with direct HTTP calls and deterministic fixtures.
- Useful for reducing Java/Python proxy split complexity.
- A good foundation for the next high-dependency group.

Still plan carefully when a group requires:

- Viewer-specific permissions.
- Namespace role resolution.
- Skill lifecycle transitions.
- File streaming or presigned storage URLs.
- Search index behavior.
- CSRF/session semantics.
- Admin-only RBAC.

## Current Completed Ownership

| Order | API / Group | Owner | Result |
| --- | --- | --- | --- |
| 0 | `GET /api/v1/health` | python | Python skeleton and envelope established. |
| 1 | `GET /.well-known/clawhub.json` | python | Plain JSON discovery route migrated with no DB dependency. |
| 2 | `GET /api/v1/labels`, `GET /api/web/labels` | python | Public labels read API migrated as first PostgreSQL-backed Python route. |
| 3 | `GET /api/v1/skills/{namespace}/{slug}/labels`, `GET /api/web/skills/{namespace}/{slug}/labels` | python | Public anonymous skill labels list migrated. Auth-specific preview remains deferred. |
| 4 | `GET /api/v1/skills/{namespace}/{slug}/resolve`, `GET /api/web/skills/{namespace}/{slug}/resolve` | python | Public anonymous version selector resolution migrated. Download remains Java-owned. |
| 5 | `GET /api/v1/skills/{namespace}/{slug}/versions`, `GET /api/web/skills/{namespace}/{slug}/versions` | python | Public anonymous published version list migrated. Version detail remains Java-owned. |
| 5.1 | `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`, `GET /api/web/skills/{namespace}/{slug}/versions/{version}` | python | Public anonymous published version detail migrated. File routes remain Java-owned. |
| 6 | `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`, `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`, `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`, `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Public anonymous skill files metadata list migrated. Content/download remain Java-owned. |
| 7 | `GET /api/v1/skills/{namespace}/{slug}`, `GET /api/web/skills/{namespace}/{slug}` | python | Public anonymous skill detail migrated. Authenticated owner/admin preview remains deferred. |
| 8 | `GET /api/web/skills` | python | Public anonymous portal search migrated. `/api/v1/skills` remains Java-owned ClawHub compatibility. |
| 9 | `GET /api/v1/search` | python | ClawHub compatibility search. `/api/v1/skills` remains Java-owned. |
| 10 | `GET /api/v1/resolve`, `GET /api/v1/resolve/{canonicalSlug}` | python | ClawHub compatibility resolve migrated. Download and ClawHub skill detail remained Java-owned during this milestone. |
| 10.5 | Method-aware Vite proxy infrastructure | n/a | Enables future GET-only migration on paths that share Java-owned mutating methods. |
| 11 | `GET /api/v1/skills/{canonicalSlug}` | python | ClawHub compatibility skill detail migrated with method-aware GET-only routing. List, publish, delete, undelete, and download remain Java-owned. |
| 12 | `GET /api/v1/skills` | python | ClawHub compatibility list migrated with method-aware GET-only routing. Root publish, delete, undelete, and download remain Java-owned. |
| 13 | `GET /api/v1/auth/me` | python | First Group C current-user bridge using local `X-Mock-User-Id`. Login, OAuth, API tokens, session bootstrap, and CLI auth remain Java-owned. |
| 14 | `GET /api/v1/skills/{namespace}/{slug}`, `GET /api/web/skills/{namespace}/{slug}` | python | Viewer-specific public skill detail capability flags migrated for local mock users. |
| 15 | `GET /api/v1/skills/{namespace}/{slug}`, `GET /api/web/skills/{namespace}/{slug}` | python | Manager-only owner preview projection migrated for public skill detail. Non-public visibility remains deferred. |
| 16 | `GET /api/v1/skills/{namespace}/{slug}/versions`, `GET /api/web/skills/{namespace}/{slug}/versions`, `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`, `GET /api/web/skills/{namespace}/{slug}/versions/{version}` | python | Manager-only owner preview access migrated for version list and version detail. File metadata/download preview access remains deferred. |
| 17 | `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`, `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files` | python | Manager-only owner preview access migrated for version file metadata. Tag preview, file bytes, and downloads remain deferred. |
| 18 | `GET /api/v1/skills/{namespace}/{slug}/resolve`, `GET /api/web/skills/{namespace}/{slug}/resolve` | python | Authenticated context forwarding and Java-compatible negative owner-preview resolve coverage completed. Non-published resolve remains rejected. |
| 19 | `GET /api/v1/skills/{namespace}/{slug}/versions/compare`, `GET /api/web/skills/{namespace}/{slug}/versions/compare` | python | Manager-only owner preview version compare migrated with Java-compatible text diff behavior. File bytes/download endpoints remain deferred. |
| 20 | `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`, `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Authenticated context forwarding and Java-compatible negative owner-preview tag file metadata coverage completed. Non-published tag targets remain rejected. |
| 21 | `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`, `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file` | python | File content read foundation migrated. Version file content supports manager-only owner preview; tag file content remains published-only. Download routes remain Java-owned. |
| 22 | `GET /api/v1/download/{canonicalSlug}`, `GET /api/v1/download`, `GET /api/v1/skills/{namespace}/{slug}/download`, `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`, `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`, `GET /api/web/skills/{namespace}/{slug}/download`, `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`, `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download` | python | Download read path migrated. ClawHub routes redirect, portal v1 and web routes stream local bundles or fallback zip entries, and published downloads increment Java-compatible counters. |
| 23 | Publish upload foundation | n/a | Python package extraction/validation helpers added. No publish POST route ownership moved; Vite detail routes are GET-only so publish POST paths remain Java-owned. |
| 24 | Publish transaction dry-run model | n/a | Python mirrors Java `validateOnly(...)` preflight decisions for namespace, membership, package, metadata, pre-publish warnings, slug, and version conflicts. No publish POST route ownership moved. |
| 25 | Publish local storage write foundation | n/a | Python writes Java-compatible local object keys, bundle zip, and future `skill_file` metadata records. No DB writes or publish POST route ownership moved. |
| 26 | Publish DB transaction foundation | n/a | Python transaction helper creates/reuses `skill`, inserts `skill_version` and `skill_file` rows, and updates version stats. No publish POST route ownership moved. |
| 27 | Publish side-effect foundation | n/a | Python helper plans/writes review task, security audit, scan task payload, publish/review event intents, and compat audit log data. No publish POST route ownership moved. |
| 28 | Publish replacement cleanup foundation | n/a | Python helper cleans replaceable non-published versions and records local storage delete compensation. No publish POST route ownership moved. |
| 29 | Publish transaction split foundation | n/a | Python DB helper supports prepare/finalize phases so storage can be written after skill/version IDs are allocated. No publish POST route ownership moved. |
| 30 | Publish orchestration foundation | n/a | Python service helper composes replacement cleanup, prepare/storage/finalize, side effects, and after-commit replacement storage deletion. No publish POST route ownership moved. |
| 31 | `POST /api/cli/v1/skills/{namespace}/publish/validate` | python | CLI publish validate-only multipart route moved to Python while all publish write routes remain Java-owned. |
| 32 | Publish CLI write direct route foundation | n/a | Python direct backend route for `POST /api/cli/v1/skills/{namespace}/publish` composes dry-run preflight and publish orchestration. Vite/proxy ownership remains Java for the write route. |
| 33 | Publish scanner handoff foundation | n/a | Python scanner-enabled publish writes Java-compatible security audit JSONB fields and publishes Redis Stream scan task fields. No publish POST route ownership moved. |
| 34 | Publish CLI replacement lookup foundation | n/a | Direct Python CLI publish route finds same-owner same-version replaceable versions and delegates cleanup to publish orchestration. No publish POST route ownership moved. |
| 35 | Publish pending-review auto-withdraw foundation | n/a | Direct Python CLI publish withdraws earlier pending-review versions for the same skill before inserting the next publish version. No publish POST route ownership moved. |
| 36 | Publish storage-failure cleanup evidence | n/a | Direct Python CLI publish has unit and live evidence that storage write failure rolls back publish database rows. No publish POST route ownership moved. |
| 37 | `POST /api/cli/v1/skills/{namespace}/publish` | python | CLI publish write ownership moved through Vite after repeated proxy publish matrix covered replacement, pending-review auto-withdraw, Java-owned portal/root route boundaries, and scanner result boundary documentation. |
| 38 | `POST /api/v1/skills/{namespace}/publish`, `POST /api/web/skills/{namespace}/publish` | python | Portal publish write aliases moved through Vite and reuse the Python publish service path. Root ClawHub and legacy publish remain Java-owned. |
| 39 | `POST /api/v1/skills`, `POST /api/v1/publish` | python | Root ClawHub payload/files publish and legacy zip+namespace publish moved through Vite. Both return plain ClawHub `{ ok, skillId, versionId }`; delete/undelete remain Java-owned. |
| 40 | Publish scanner result processing foundation | n/a | Python can apply normalized scanner results to the latest active security audit and Java-compatible `SCANNING` status transitions. Redis consumer/worker remains deferred. |
| 41 | Publish scan task worker boundary | n/a | Python can parse Java-compatible Redis scan task fields, stage local bundle objects, call a scanner abstraction, apply scan results, clean staged files, and mark still-`SCANNING` versions `SCAN_FAILED` on processing failure. Long-running consumer/retry/reclaim remains deferred. |
| 42 | Publish scan consumer runtime | n/a | Python can create Redis consumer groups, consume never-delivered scan tasks, ACK success/invalid/retry/final-failure messages, republish retries up to Java's max retry count, and reclaim pending messages for one-pass processing. Daemon lifecycle and scanner HTTP client remain deferred. |
| 43 | Publish scanner HTTP client | n/a | Python scan consumer can call the real scanner service in upload/local modes, map Java-compatible scanner responses into scanner result input, and pass live Redis consumer verification with the scanner container. Daemon lifecycle remains deferred. |
| 44 | Publish scan daemon/supervisor integration | n/a | Python FastAPI can optionally start a background scan consumer daemon, ensure its Redis consumer group exists before polling, consume scanner tasks through the real scanner container, update audit/version status, ACK messages, and shut down with the hybrid stack. No route ownership moved. |
| 45 | `POST /api/v1/reviews/{id}/approve`, `POST /api/web/reviews/{id}/approve` | python | Review approval write ownership moved to Python. The route publishes the reviewed version, updates `skill.latest_version_id`, visibility, metadata, and `updated_by`, records `REVIEW_APPROVE` audit, and passed Java/Python/Vite v1/web live comparison. Reject, withdraw, submit, list, detail, review-file, and review-download routes remain Java-owned. |
| 46 | `POST /api/v1/reviews/{id}/reject`, `POST /api/web/reviews/{id}/reject`, `POST /api/v1/reviews/{id}/withdraw`, `POST /api/web/reviews/{id}/withdraw` | python | Review reject and withdraw write ownership moved to Python. Reject records reviewer/comment, moves review task/version to `REJECTED`, and writes `REVIEW_REJECT` audit. Withdraw is submitter-only, deletes the pending review task, reopens the version to `UPLOADED`, updates skill `updated_by`, and writes `REVIEW_WITHDRAW` audit. Submit, list, detail, review-file, review-download, and promotion review routes remain Java-owned. |
| 47 | `POST /api/v1/reviews`, `POST /api/web/reviews` | python | Review submit write ownership moved to Python. The route moves eligible versions to `PENDING_REVIEW`, creates the pending review task, and writes `REVIEW_SUBMIT` audit. |
| 48 | `GET /api/v1/reviews`, `GET /api/web/reviews`, `GET /api/v1/reviews/pending`, `GET /api/web/reviews/pending`, `GET /api/v1/reviews/my-submissions`, `GET /api/web/reviews/my-submissions` | python | Review list read ownership moved to Python with Java-compatible page envelopes and review authorization. |
| 49 | `GET /api/v1/reviews/{id}`, `GET /api/web/reviews/{id}` | python | Review task detail read ownership moved to Python with submitter, namespace reviewer, and platform reviewer visibility parity. |
| 50 | `GET /api/v1/reviews/{id}/skill-detail`, `GET /api/web/reviews/{id}/skill-detail` | python | Review-bound skill detail read ownership moved to Python. The route uses the task's active skill version, Java lifecycle version ordering, storage-backed README/SKILL documentation, and keeps review file/download Java-owned. |
| 51 | `GET /api/v1/reviews/{id}/file`, `GET /api/web/reviews/{id}/file` | python | Review-bound single-file content moved to Python. The route validates Java-invalid paths, returns raw octet-stream bytes from the review task's active version, and keeps review download Java-owned. |
| 52 | `GET /api/v1/reviews/{id}/download`, `GET /api/web/reviews/{id}/download` | python | Review-bound package download moved to Python. The route streams the review task's active version prebuilt bundle or fallback zip, preserves attachment headers/content length, and does not increment public download counters. |
| 53 | `GET /api/v1/promotions`, `GET /api/web/promotions`, `GET /api/v1/promotions/pending`, `GET /api/web/promotions/pending`, `GET /api/v1/promotions/{id}`, `GET /api/web/promotions/{id}` | python | Promotion read ownership moved to Python. List/pending require platform review role; detail allows submitter or platform review role. Promotion write routes remained Java-owned during this milestone. |
| 54 | `POST /api/v1/promotions`, `POST /api/web/promotions`, `POST /api/v1/promotions/{id}/reject`, `POST /api/web/promotions/{id}/reject` | python | Promotion submit and reject write ownership moved to Python. Submit creates pending requests and `PROMOTION_SUBMIT` audit; reject is platform-reviewer only, writes `PROMOTION_REJECT` audit and synchronous governance notification. Promotion approve remains Java-owned. |
| 55 | `POST /api/v1/promotions/{id}/approve`, `POST /api/web/promotions/{id}/approve` | python | Promotion approve ownership moved to Python. Approval materializes target global skill/version/file records, updates `promotion_request.target_skill_id`, writes `PROMOTION_APPROVE` audit and synchronous governance notification. |
| 56 | `POST /api/v1/skills/{namespace}/{slug}/archive`, `POST /api/web/skills/{namespace}/{slug}/archive`, `POST /api/v1/skills/{namespace}/{slug}/unarchive`, `POST /api/web/skills/{namespace}/{slug}/unarchive` | python | Portal skill archive/unarchive ownership moved to Python. Owner or namespace manager toggles `skill.status`, updates `updated_by`, and writes Java-compatible lifecycle audit logs. Version delete, rerelease, submit-review, confirm-publish, admin hide/unhide, and yank remained Java-owned at this milestone. |
| 57 | `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}`, `DELETE /api/web/skills/{namespace}/{slug}/versions/{version}` | python | Portal version delete ownership moved to Python. Deletes allowed non-published statuses, clears file metadata, soft-deletes security audit rows, recalculates latest published pointer, writes `DELETE_SKILL_VERSION` audit, deletes local storage with compensation, and resolves the observed Vite DELETE version proxy boundary by making the route Python-owned. |
| 58 | `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`, `POST /api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | python | Portal version withdraw-review ownership moved to Python. The pending review task submitter can delete the pending task, reopen the version to `UPLOADED`, update `skill.updated_by`, and write `REVIEW_WITHDRAW` audit. |
| 59 | `POST /api/v1/skills/{namespace}/{slug}/confirm-publish`, `POST /api/web/skills/{namespace}/{slug}/confirm-publish` | python | Portal confirm-publish ownership moved to Python. Owner or namespace manager can directly publish PRIVATE `UPLOADED`/`DRAFT` versions, update `published_at`, skill latest pointer, `updated_by`, and write `CONFIRM_PUBLISH` audit. |
| 60 | `POST /api/v1/skills/{namespace}/{slug}/submit-review`, `POST /api/web/skills/{namespace}/{slug}/submit-review` | python | Portal submit-review ownership moved to Python. Owner or namespace manager can move `UPLOADED`/`DRAFT` versions to `PENDING_REVIEW`, persist target visibility, create pending review tasks, and write `SUBMIT_REVIEW` audit. |
| 61 | `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`, `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease` | python | Portal rerelease ownership moved to Python. Owner or namespace manager can rebuild a target version from a published source version, rewrite `SKILL.md` version, reuse publish orchestration, and write `RERELEASE_SKILL_VERSION` audit. |
| 62 | `POST /api/v1/admin/skills/{skillId}/hide`, `POST /api/v1/admin/skills/{skillId}/unhide` | python | Platform-admin skill hide/unhide ownership moved to Python. `SUPER_ADMIN` can toggle the hidden overlay without changing `skill.status`, update audit fields, and write Java-compatible `HIDE_SKILL`/`UNHIDE_SKILL` audit logs. Admin version yank remains Java-owned. |
| 63 | `POST /api/v1/admin/skills/versions/{versionId}/yank` | python | Admin version yank ownership moved to Python. `SKILL_ADMIN` or `SUPER_ADMIN` can yank a `PUBLISHED` version, set yanked fields, disable download readiness, recalculate `skill.latest_version_id` when the yanked version was latest, and write `YANK_SKILL_VERSION` audit. |
| 64 | `GET /api/v1/skills/{skillId}/star`, `GET /api/web/skills/{skillId}/star`, `PUT /api/v1/skills/{skillId}/star`, `PUT /api/web/skills/{skillId}/star` | python | Skill star read/create ownership moved to Python. Anonymous reads stay rejected to match live Java security, repeated star is idempotent, `skill.star_count` refreshes synchronously, and DELETE star remains Java-owned/deferred because live v1 security blocks normal users. |
| 65 | `GET /api/v1/skills/{skillId}/subscription`, `GET /api/web/skills/{skillId}/subscription`, `PUT /api/v1/skills/{skillId}/subscription`, `PUT /api/web/skills/{skillId}/subscription` | python | Skill subscription read/create ownership moved to Python. Anonymous reads return false to match live Java behavior, repeated subscribe is idempotent, `skill.subscription_count` increments once, and DELETE subscription remains Java-owned/deferred because live v1 security blocks normal users. |
| 66 | `GET /api/v1/skills/{skillId}/rating`, `GET /api/web/skills/{skillId}/rating`, `PUT /api/v1/skills/{skillId}/rating`, `PUT /api/web/skills/{skillId}/rating` | python | Skill rating read/create/update ownership moved to Python. Anonymous reads stay rejected to match live Java security, score 1..5 is validated, same-user rating updates reuse the existing row, and `skill.rating_avg` / `skill.rating_count` refresh synchronously. |
| 67 | `GET /api/v1/me/stars`, `GET /api/web/me/stars`, `GET /api/v1/me/subscriptions`, `GET /api/web/me/subscriptions` | python | Current-user social list reads moved to Python. Requires auth, preserves Java `page=0&size=12` defaults and page envelope, filters missing skills from `items` while preserving relationship-table total, and keeps `/me/skills` Java-owned. |
| 68 | `DELETE /api/v1/skills/{skillId}/star`, `DELETE /api/web/skills/{skillId}/star`, `DELETE /api/v1/skills/{skillId}/subscription`, `DELETE /api/web/skills/{skillId}/subscription` | python | Social delete cleanup moved unstar/unsubscribe to Python. Both actions require auth, remain idempotent, update counters, and intentionally follow Java controller/domain behavior instead of the live Java v1 broad hard-delete security mismatch. |
| 69 | `GET /api/v1/notifications`, `GET /api/web/notifications`, `GET /api/v1/notifications/unread-count`, `GET /api/web/notifications/unread-count`, `PUT /api/v1/notifications/{id}/read`, `PUT /api/web/notifications/{id}/read`, `PUT /api/v1/notifications/read-all`, `PUT /api/web/notifications/read-all`, `DELETE /api/v1/notifications/{id}`, `DELETE /api/web/notifications/{id}` | python | Notification read/read-state ownership moved to Python. Requires auth, preserves Java `PageResponse` and `{ count }` / `{ updated }` shapes, keeps mark-one-read success `data = null`, and leaves SSE/preferences Java-owned. |
| 70 | `GET /api/v1/notification-preferences`, `GET /api/web/notification-preferences`, `PUT /api/v1/notification-preferences`, `PUT /api/web/notification-preferences` | python | Notification preference ownership moved to Python. Requires auth, returns Java enum-order `IN_APP` preferences with missing rows defaulting enabled, validates category/channel/duplicate payloads, and keeps notification SSE Java-owned. |
| 71 | `GET /api/v1/me/skills`, `GET /api/web/me/skills` | python | Current-user owned skill list moved to Python. Preserves Java `page=0&size=10`, filter/q/namespace behavior, owner summary lifecycle projection, default direct owner list including hidden/archived, and filter-path hidden/archived exclusion semantics. |
| 72 | `GET /api/v1/namespaces`, `GET /api/web/namespaces`, `GET /api/v1/me/namespaces`, `GET /api/web/me/namespaces`, `GET /api/v1/namespaces/{slug}`, `GET /api/web/namespaces/{slug}` | python | Namespace read ownership moved to Python. Preserves membership-scoped active listing, current-user namespace capability flags, archived namespace member-only detail visibility, and keeps namespace lifecycle/mutation routes Java-owned. |
| 73 | `GET /api/v1/namespaces/{slug}/members`, `GET /api/web/namespaces/{slug}/members`, `GET /api/v1/namespaces/{slug}/member-candidates`, `GET /api/web/namespaces/{slug}/member-candidates` | python | Namespace member read ownership moved to Python. Preserves membership/admin checks, Java candidate search normalization, ACTIVE user filtering, existing-member exclusion, and keeps namespace member mutations Java-owned. |
| 74 | `POST /api/v1/namespaces/{slug}/members`, `POST /api/web/namespaces/{slug}/members`, `DELETE /api/v1/namespaces/{slug}/members/{userId}`, `DELETE /api/web/namespaces/{slug}/members/{userId}`, `PUT /api/v1/namespaces/{slug}/members/{userId}/role`, `PUT /api/web/namespaces/{slug}/members/{userId}/role`, `POST /api/v1/namespaces/{slug}/members/batch`, `POST /api/web/namespaces/{slug}/members/batch` | python | Namespace member mutation ownership moved to Python. Preserves Java active-team/admin-or-owner checks, owner role protections, duplicate/missing-member errors, and batch partial-success mapping. |
| 75 | `POST /api/v1/namespaces/{slug}/transfer-ownership`, `POST /api/web/namespaces/{slug}/transfer-ownership` | python | Namespace ownership transfer moved to Python. Preserves Java `TEAM`/`ACTIVE` transferability, current-owner validation, new-owner membership validation, and role swap semantics. |
| 76 | `POST /api/v1/namespaces`, `POST /api/web/namespaces`, `PUT /api/v1/namespaces/{slug}`, `PUT /api/web/namespaces/{slug}`, `DELETE /api/v1/namespaces/{slug}`, `DELETE /api/web/namespaces/{slug}`, `POST /api/v1/namespaces/{slug}/freeze`, `POST /api/web/namespaces/{slug}/freeze`, `POST /api/v1/namespaces/{slug}/unfreeze`, `POST /api/web/namespaces/{slug}/unfreeze`, `POST /api/v1/namespaces/{slug}/archive`, `POST /api/web/namespaces/{slug}/archive`, `POST /api/v1/namespaces/{slug}/restore`, `POST /api/web/namespaces/{slug}/restore` | python | Namespace profile and lifecycle mutations moved to Python. Preserves platform-role create, owner/admin update, owner-only delete, dependency guard, lifecycle state transitions, and namespace audit logs. |
| 77 | `GET /api/v1/admin/labels`, `POST /api/v1/admin/labels`, `PUT /api/v1/admin/labels/{slug}`, `DELETE /api/v1/admin/labels/{slug}`, `PUT /api/v1/admin/labels/sort-order` | python | Admin label definition management moved to Python. Preserves `SUPER_ADMIN` guard, slug/translation normalization, create/update/delete/sort DB effects, and admin label audit logs. |
| 78 | `GET /api/v1/admin/users`, `PUT /api/v1/admin/users/{userId}/role`, `PUT /api/v1/admin/users/{userId}/status`, `POST /api/v1/admin/users/{userId}/approve`, `POST /api/v1/admin/users/{userId}/disable`, `POST /api/v1/admin/users/{userId}/enable` | python | Admin user management basics moved to Python. Preserves `USER_ADMIN`/`SUPER_ADMIN` guard, list filters/page envelope, role replacement semantics, and status aliases. |
| 79 | `GET /api/v1/governance/summary`, `GET /api/web/governance/summary`, `GET /api/v1/governance/inbox`, `GET /api/web/governance/inbox`, `GET /api/v1/governance/activity`, `GET /api/web/governance/activity`, `GET /api/v1/governance/notifications`, `GET /api/web/governance/notifications` | python | Governance workbench read APIs moved to Python. Preserves Java summary counts, inbox merge projections, activity visibility, and legacy `user_notification` list behavior. |
| 80 | `GET /api/v1/admin/audit-logs` | python | Admin audit log read moved to Python. Preserves `AUDITOR`/`SUPER_ADMIN` guard, dynamic filters, details fallback, UTC timestamp handling, and page envelope. |
| 81 | `GET /api/v1/admin/skill-reports`, `GET /api/v1/admin/profile-reviews` | python | Admin report/review list reads moved to Python. Preserves platform-role guards, status parsing, skill/report and profile-review projections, profile JSON fallback, sort behavior, and keeps admin report/profile mutation routes Java-owned. |
| 82 | `POST /api/v1/admin/skill-reports/{reportId}/resolve`, `POST /api/v1/admin/skill-reports/{reportId}/dismiss`, `POST /api/v1/admin/profile-reviews/{id}/approve`, `POST /api/v1/admin/profile-reviews/{id}/reject` | python | Admin report/profile review mutations moved to Python. Preserves Java role guards, pending-only transitions, report notifications, audit logs, skill hide/archive side effects, profile display-name application, and method-aware proxy ownership. |
| 83 | `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`, `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`, `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`, `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}` | python | Skill label attach/detach moved to Python. Preserves Java owner/namespace-admin/super-admin permission rules, privileged-label restriction, max-label and missing-label errors, Java envelopes, and skill-label audit logs. |
| 84 | `POST /api/v1/governance/notifications/{id}/read`, `POST /api/web/governance/notifications/{id}/read` | python | Legacy governance notification mark-read moved to Python. Preserves Java `user_notification` ownership checks, not-found/forbidden errors, `READ`/`read_at` mutation, and `更新成功` envelope. |

| 85 | `POST /api/v1/admin/users/{userId}/password-reset` | python | Admin-triggered local password reset moved to Python. Preserves admin role guard, Java eligibility errors, BCrypt-compatible code hashes, pending-request consumption, and admin metadata. |
| 86 | `POST /api/v1/stars/{canonicalSlug}`, `DELETE /api/v1/stars/{canonicalSlug}` | python | ClawHub compatibility star/unstar moved to Python. Preserves Java canonical slug mapping, visible skill lookup, idempotent `alreadyStarred`/`alreadyUnstarred` fields, plain ClawHub JSON responses, and synchronized `skill.star_count`. |
| 86 | `POST /api/v1/tokens`, `GET /api/v1/tokens`, `DELETE /api/v1/tokens/{id}`, `PUT /api/v1/tokens/{id}/expiration` | python | API token self-service management moved to Python. Preserves current-user guard, create/rotate semantics, SHA-256 hash-only storage, active owner-scoped listing, owner-scoped revoke, and expiration validation. Bearer token scope enforcement is completed in order 100. |
| 87 | `POST /api/v1/auth/local/password-reset/request`, `POST /api/v1/auth/local/password-reset/confirm` | python | Anonymous local password reset request/confirm moved to Python. Preserves Java normalization, validation, silent request success for unknown/ineligible users, BCrypt reset code storage, password policy, credential reset, and pending reset request consumption while local register/login/change-password remain Java-owned. |
| 88 | `GET /api/v1/auth/providers`, `GET /api/v1/auth/methods` | python | Public auth catalog reads moved to Python. Preserves Java OAuth provider sorting, method ordering, default-disabled direct/session-bootstrap entries, authorization URLs, and safe `returnTo` sanitization while login/session/OAuth callbacks remain Java-owned. |
| 89 | `GET /api/v1/whoami`, `GET /api/cli/v1/auth/whoami` | python | Current-principal whoami reads moved to Python. Preserves ClawHub plain JSON and CLI `ApiResponse` envelope shapes while keeping session/OAuth callbacks and bearer-token authentication filters Java-owned. |
| 90 | `POST /api/v1/skills/{namespace}/{slug}/reports`, `POST /api/web/skills/{namespace}/{slug}/reports` | python | Skill report submit moved to Python. Preserves Java published-preference target resolution, blank/self/duplicate/unavailable validation, pending report insert, `REPORT_SKILL` audit, and `REPORT_SUBMITTED` notification side effects. |
| 91 | `POST /api/v1/auth/local/register`, `POST /api/v1/auth/local/login`, `POST /api/v1/auth/local/change-password` | python | Local auth core moved to Python. Preserves Java local account normalization/validation, BCrypt credential handling, failed-attempt lockout/reset, password policy, global namespace membership on register, and hybrid mock-user change-password behavior while keeping Spring Session creation deferred. |
| 92 | `POST /api/v1/auth/direct/login`, `POST /api/v1/auth/session/bootstrap` | python | Direct login and session bootstrap boundaries moved to Python. Preserves Java default-disabled 403 behavior and unsupported-provider ordering. Direct local can reuse migrated local login response, while final cookie/session persistence and passive bootstrap success remain deferred. |
| 93 | `GET /api/v1/notifications/sse`, `GET /api/web/notifications/sse` | python | Notification SSE connection boundary moved to Python. Preserves auth rejection, `text/event-stream`, connected event, and heartbeat comment shape. Active notification fanout remains deferred to a Python dispatcher/refactor milestone. |
| 94 | `GET /api/cli/v1/skills/search`, `GET /api/cli/v1/skills/{namespace}/{slug}/resolve`, `GET /api/cli/v1/skills/{namespace}/{slug}/download`, `GET /api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download` | python | CLI skill read/download compatibility moved to Python. Preserves Java `ApiResponse` search/resolve envelopes, download stream/header behavior, and explicitly keeps destructive `DELETE /api/cli/v1/skills/{namespace}/{slug}` Java-owned. |
| 95 | `GET /api/v1/skills/{namespace}/{slug}/tags`, `GET /api/web/skills/{namespace}/{slug}/tags`, `PUT /api/v1/skills/{namespace}/{slug}/tags/{tagName}`, `PUT /api/web/skills/{namespace}/{slug}/tags/{tagName}`, `DELETE /api/v1/skills/{namespace}/{slug}/tags/{tagName}`, `DELETE /api/web/skills/{namespace}/{slug}/tags/{tagName}` | python | Skill tag management moved to Python. Preserves Java visibility checks, virtual `latest` list tag, namespace `OWNER`/`ADMIN` write guard, reserved `latest` rejection, published-target requirement, and live Java success messages. |
| 96 | `DELETE /api/v1/skills/id/{skillId}`, `DELETE /api/v1/skills/{namespace}/{slug}`, `DELETE /api/web/skills/id/{skillId}`, `DELETE /api/web/skills/{namespace}/{slug}` | python | Whole-skill hard delete moved to Python. Preserves v1 `SUPER_ADMIN` guard, web owner-or-super-admin guard, slug idempotent `deleted=false`, DB artifact cleanup, `DELETE_SKILL_HARD` audit, local storage deletion, and ClawHub delete/undelete Java ownership. |
| 97 | `POST /api/v1/account/merge/initiate`, `POST /api/v1/account/merge/verify`, `POST /api/v1/account/merge/confirm` | python | Account merge workflow moved to Python. Preserves mock-user auth requirement, local username/provider-subject secondary resolution, pending/local-credential conflict checks, BCrypt token hashing/verification, and atomic confirm side effects for bindings, tokens, roles, namespace memberships, credentials, primary email fill, secondary `MERGED`, and request completion. |
| 98 | `POST /api/v1/auth/device/code`, `POST /api/v1/device/authorize`, `POST /api/v1/auth/device/token` | python | CLI/browser device authorization flow moved to Python. Preserves Java code payload shape, Redis key/TTL semantics, user-code authorization state machine, `DEVICE_AUTHORIZE` audit, one-time token redemption, `CLI Device Flow` API token rotation, and `skill:read`/`skill:publish` scopes. Windows live gate also records the current Java runtime token-poll `ClassCastException` as a pre-existing reference defect while Python/proxy full flow passes. |
| 99 | Bearer-token current-principal bridge for `GET /api/v1/auth/me`, `GET /api/v1/whoami`, `GET /api/cli/v1/auth/whoami` | python | Existing Python-owned current-principal routes now accept Java-compatible bearer tokens after `X-Mock-User-Id` precedence. Preserves SHA-256 token lookup, active token/user checks, `api_token` provider projection, platform-role fallback/projection, and `last_used_at` touch. Global bearer scope enforcement remains deferred. |
| 100 | Bearer-token `token:manage` scope enforcement for `/api/v1/tokens*` | python | Already Python-owned token management routes now reject bearer `api_token` principals without `token:manage` with Java-compatible `403`, keep bad bearer tokens at `401`, and preserve mock-user precedence. Broader route-policy scope enforcement remains deferred. |

## Revised Pre-Launch Milestone Order

The earlier migrations intentionally used small public GET endpoints to establish Python
infrastructure, Vite route ownership, Windows live verification, and Java/Python contract
comparison. Those completed milestones remain valid and are listed above.

From this point forward, migration should use larger, cohesive milestones. Each milestone must
still be small enough to verify end-to-end before commit/push.

### Group A. Finish Public Catalog Read Ownership

Goal:

- Make Python the clear owner for public browsing and ClawHub read-only compatibility.
- Reduce Vite proxy fragmentation around already-migrated read routes.

Already Python-owned in this group:

- `GET /api/web/skills`
- `GET /api/web/labels`
- `GET /api/v1/labels`
- `GET /api/v1/search`
- `GET /api/v1/skills`
- `GET /api/v1/resolve`
- `GET /api/v1/resolve/{canonicalSlug}`
- `GET /api/v1/skills/{canonicalSlug}`
- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`
- `GET /api/v1/skills/{namespace}/{slug}/labels`
- `GET /api/web/skills/{namespace}/{slug}/labels`
- `GET /api/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/web/skills/{namespace}/{slug}/resolve`
- `GET /api/v1/skills/{namespace}/{slug}/versions`
- `GET /api/web/skills/{namespace}/{slug}/versions`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files`

Note: tag file metadata routes are Python-owned but remain published-only for tag selectors.
Java's tag path does not call owner-preview access checks, so owners/admins are still rejected for
non-published tag targets.

Remaining candidate in this group:

- None after the ClawHub list milestone completes and its result is committed.

Keep Java-owned in this group:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- all download/file-content routes.

Acceptance focus:

- `GET /api/v1/skills` plain ClawHub list matches Java.
- Root `POST /api/v1/skills` is now Python-owned after publish ownership order 39.
- Existing Python read routes stay green.
- Vite proxy rules become simpler where possible, but method collisions remain explicitly tested.

### Group B. File Content And Download Read Path

Goal:

- Move file content and download routes to Python through two storage/read milestones.
- Establish file-byte read behavior before download counters and bundle/download headers.

Completed milestone: File Content Read Foundation

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`

This milestone is intentionally larger than one API but smaller than the full download workflow.
It establishes the Python local object-storage read helper, raw byte responses, content-type
parity, owner-preview version file access, and Java-compatible published-only tag file behavior.

Completed milestone: Download Read Path

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-download-read-path.md`
- `GET /api/v1/download/{canonicalSlug}`
- `GET /api/v1/download?slug={slug}&version={version}`
- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`

The download milestone started only after file content reads had a passing live gate.

Routes intentionally not grouped with file content:

- `GET /api/v1/download/{canonicalSlug}`
- `GET /api/v1/download?slug={slug}&version={version}`
- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`

Routes intentionally not migrated with download read path:

- `GET /api/web/skills/{namespace}/{slug}/download`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download`

Bridge design required before implementation:

- Object storage abstraction for Python: local file first, MinIO/S3-compatible behavior later.
- Redirect vs stream behavior and headers for download routes.
- Download counter behavior for download routes.
- Rate-limit assumptions.
- Missing object fallback behavior.
- Live fixture including stored file bytes.

Acceptance focus:

- Java/Python/Vite contract comparison for status, content type, and file bytes in the file
  content milestone.
- Java/Python/Vite contract comparison for headers, status, redirects or streamed bytes, and
  counters in the download milestone.
- No schema change under Python unless explicitly planned.
- Download metrics behavior is documented and tested.

Download read path live findings:

- Java and Python both allow public skill downloads for `PUBLISHED`, `UPLOADED`, and
  `PENDING_REVIEW`; only other statuses are `error.skill.version.notDownloadable`.
- Counters increment only for `PUBLISHED` successful portal downloads.
- Direct bundle bytes must match exactly.
- Fallback zip comparison validates zip entry names and entry bytes rather than raw zip bytes,
  because Java and Python can produce different valid zip container byte streams.

### Group C. Auth And Current User Bridge

Goal:

- Establish the minimum Python auth/session model required for internal use before migrating
  viewer-specific reads or mutations.

Python-owned in this group:

- `GET /api/v1/auth/me`
- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`
- viewer-specific capability flags for `GET /api/v1/skills/{namespace}/{slug}`
- viewer-specific capability flags for `GET /api/web/skills/{namespace}/{slug}`
- manager-only owner preview projection for `GET /api/v1/skills/{namespace}/{slug}`
- manager-only owner preview projection for `GET /api/web/skills/{namespace}/{slug}`
- manager-only owner preview version list access for `GET /api/v1/skills/{namespace}/{slug}/versions`
- manager-only owner preview version list access for `GET /api/web/skills/{namespace}/{slug}/versions`
- manager-only owner preview version detail access for
  `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- manager-only owner preview version detail access for
  `GET /api/web/skills/{namespace}/{slug}/versions/{version}`
- manager-only owner preview version file metadata access for
  `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- manager-only owner preview version file metadata access for
  `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`
- authenticated context forwarding and published-only resolve parity for
  `GET /api/v1/skills/{namespace}/{slug}/resolve`
- authenticated context forwarding and published-only resolve parity for
  `GET /api/web/skills/{namespace}/{slug}/resolve`
- manager-only owner preview version compare for
  `GET /api/v1/skills/{namespace}/{slug}/versions/compare`
- manager-only owner preview version compare for
  `GET /api/web/skills/{namespace}/{slug}/versions/compare`

Still Java-owned/deferred in this group:

- OAuth callback/session establishment paths not explicitly moved to Python.
- Global bearer-token scope enforcement outside the current-principal read bridge.
- `/oauth2/**`

Next candidate routes:

- Namespace/platform role resolution helpers needed by protected frontend workflows.
- Local session-aware request context if internal development needs cookie-based web login before
  publish/upload migration.
- Viewer-specific list/search capability flags if the frontend needs them before publish/upload.
- Owner-preview access for tag file metadata or download routes if the frontend needs those before
  publish/upload. Portal resolve was checked and remains Java-compatible published-only behavior.

Bridge design required before implementation:

- Whether Python temporarily reads Java session state, replaces it, or uses a simplified internal
  auth model.
- CSRF handling for mutating web APIs.
- `X-Mock-User-Id` local behavior.
- Organization internal identity assumptions.
- Test users and fixtures.

Acceptance focus:

- Frontend can run against Python-owned auth context for migrated workflows.
- Protected route behavior is explicit and tested.
- OAuth remains Java-owned unless the milestone explicitly moves it.

### Group D. Skill Publish / Upload Vertical Slice

Goal:

- Move package upload, validation, scanner handoff, storage write, and initial version creation to
  Python as one coherent workflow.

Completed foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-upload-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-upload-foundation.md`
- Scope:
  Python package extraction and validation helpers only.
- Route ownership:
  no publish POST route ownership changes.
- Proxy boundary:
  two-segment skill detail routes are method-aware GET-only so
  `POST /api/v1/skills/{namespace}/publish` and `POST /api/web/skills/{namespace}/publish` fall
  through to Java.
- Explicitly Java-owned during this foundation:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/{namespace}/publish`
  - `POST /api/web/skills/{namespace}/publish`
  - `POST /api/cli/v1/skills/{namespace}/publish/validate`
  - `POST /api/cli/v1/skills/{namespace}/publish`

Completed dry-run model milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-dry-run-model.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-dry-run-model.md`
- Scope:
  Python dry-run preflight model only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented checks:
  namespace existence/status, namespace membership with `SUPER_ADMIN` bypass, package validation,
  metadata slug/version resolution, Java-compatible basic credential warning scan, own archived
  skill, own published version conflict, and other-owner published name conflict.
- Explicitly not implemented:
  DB writes, object storage writes, review task creation, scanner trigger, audit/event behavior,
  and publish HTTP route ownership.

Completed local storage write foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-local-storage-write-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-local-storage-write-foundation.md`
- Scope:
  Python local object-storage write helpers only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  Java-compatible file object keys, bundle object key, SHA-256 metadata, file count/total size
  stats, bundle zip bytes, local path safety checks, and future `skill_file` row metadata.
- Explicitly not implemented:
  `skill`, `skill_version`, or `skill_file` DB writes, scanner trigger, review task creation,
  audit/event behavior, replacement cleanup, and publish HTTP route ownership.

Completed DB transaction foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-db-transaction-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-db-transaction-foundation.md`
- Scope:
  Python DB transaction helper only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  Java-compatible initial version status selection, parsed metadata JSON, manifest JSON, create or
  reuse `skill`, archived-skill rejection, `skill_version` insert, `skill_file` inserts, version
  file stats update, bundle/download readiness flags, and `latest_version_id` update only for
  `PUBLISHED` or `UPLOADED` versions.
- Explicitly not implemented:
  publish HTTP route ownership, scanner trigger, review task creation, audit/event behavior,
  replacement cleanup, storage compensation, CSRF/session behavior, and live DB mutation through
  an HTTP route.

Completed side-effect foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-side-effect-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-side-effect-foundation.md`
- Scope:
  Python publish side-effect helpers only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  Java-compatible review task decision for `PENDING_REVIEW`, `ReviewSubmittedEvent` intent,
  `SkillPublishedEvent` intent for `PUBLISHED`, scanner audit row seed values, scan task payload
  shape for upload/local modes, non-published `SCANNING` transition when scanner is enabled, and
  ClawHub `COMPAT_PUBLISH` audit log payload.
- Explicitly not implemented:
  publish HTTP route ownership, actual scanner HTTP calls, Redis stream publishing, notification
  delivery, replacement cleanup, storage compensation, CSRF/session behavior, and live Python DB
  mutation through an HTTP route.

Completed replacement cleanup foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-replacement-cleanup-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-replacement-cleanup-foundation.md`
- Scope:
  Python replacement cleanup and local storage delete compensation helpers only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  Java-compatible rejection for replacing `PUBLISHED` versions, latest-version FK clearing,
  pending review task deletion, file storage-key collection plus bundle key, `skill_file` deletion,
  security audit soft delete, `skill_version` deletion, local object deletion, and
  `skill_storage_delete_compensation` pending record creation when local deletion fails.
- Explicitly not implemented:
  publish HTTP route ownership, live DB mutation through a Python route, MinIO/S3 delete,
  after-commit hook orchestration, and integration into the publish transaction helper.

Completed transaction split foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-transaction-split-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-transaction-split-foundation.md`
- Scope:
  Python DB transaction helper split only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  `prepare_publish_db_records(...)` creates or reuses `skill`, inserts `skill_version`, and
  returns `skill_id` / `version_id` before storage writes; `finalize_publish_db_records(...)`
  inserts `skill_file` rows, updates version stats/readiness flags, and updates skill metadata or
  `latest_version_id`; the existing `create_publish_db_records(...)` wrapper preserves the prior
  one-call transaction behavior for tests and future callers.
- Explicitly not implemented:
  publish HTTP route ownership, storage write orchestration, scanner trigger, side-effect
  orchestration, replacement cleanup orchestration, CSRF/session behavior, and live DB mutation
  through a Python route.

Completed orchestration foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-orchestration-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-orchestration-foundation.md`
- Scope:
  Python publish service orchestration helper only.
- Route ownership:
  no publish POST route ownership changes.
- Implemented behavior:
  `execute_publish_write(...)` optionally cleans replaceable non-published versions, prepares DB
  records, writes local storage objects after IDs are allocated, finalizes file rows/stats, applies
  side effects, commits, then deletes old replacement storage with compensation support.
- Explicitly not implemented:
  publish HTTP route ownership, multipart request parsing, dry-run HTTP route, scanner HTTP call,
  Redis stream delivery, CSRF/session behavior, and live DB mutation through a Python route.

Completed HTTP validate route adapter milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-http-validate-route.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-http-validate-route.md`
- Scope:
  Python CLI publish validate-only HTTP adapter.
- Route ownership:
  moved only `POST /api/cli/v1/skills/{namespace}/publish/validate` to Python.
- Keep Java-owned:
  all publish routes that write DB rows, storage objects, scanner tasks, audit logs, or lifecycle
  state.
- Acceptance focus:
  multipart upload parsing, Java-compatible dry-run response data, Vite proxy ownership for the
  validate route only, and live proof that publish write routes still reach Java.

Completed CLI write direct route foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-publish-cli-write-direct-route-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-publish-cli-write-direct-route-foundation.md`
- Scope:
  Python direct backend implementation for `POST /api/cli/v1/skills/{namespace}/publish`.
- Route ownership:
  no ownership change. Vite proxy and route registry still keep this write route Java-owned.
- Implemented behavior:
  direct Python multipart write route uses dry-run preflight, local mock auth bridge, package
  extraction, namespace authorization lookup, publish orchestration, local object storage writes,
  DB inserts/updates, and side-effect helpers for the new-version happy path.
- Explicitly not implemented:
  scanner HTTP handoff, same-version replacement lookup from the HTTP route, pending review
  auto-withdraw before replacement, and full repeated publish route ownership matrix.
- Acceptance focus:
  direct Java/Python write comparison for stable publish response fields, live Python DB/storage
  write, and proof that proxy write traffic still reaches Java.

Completed scanner handoff foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-09-publish-scanner-handoff-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-09-publish-scanner-handoff-foundation.md`
- Scope:
  Python scanner handoff foundation for publish orchestration.
- Route ownership:
  no ownership change. Publish write routes remain Java-owned through Vite/proxy.
- Implemented behavior:
  scanner-enabled Python publish writes JSONB-safe `security_audit` fields, generates a UUID
  `taskId` when absent, builds Java-compatible `ScanTask` fields, and publishes them to Redis
  Stream `skillhub:scan:requests` in upload mode.
- Explicitly not implemented:
  scanner consumer/result processing, retry/reclaim behavior, scanner HTTP calls, and route
  ownership move.
- Acceptance focus:
  direct Python publish writes a fixture, Redis stream contains Java-compatible fields, and
  Playwright smoke remains green.

Completed CLI replacement lookup foundation milestone:

- Plan:
  `docs/backend-python-migration/plans/2026-06-09-publish-cli-replacement-lookup-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-09-publish-cli-replacement-lookup-foundation.md`
- Scope:
  route-level replacement lookup for direct Python CLI publish.
- Route ownership:
  no ownership change. Publish write routes remain Java-owned through Vite/proxy.
- Implemented behavior:
  direct Python publish finds an existing same-owner same-slug same-version row, maps it to
  `ReplaceableVersion`, and passes it into existing publish orchestration. Live verification proves
  a second direct Python publish replaces the first version row and deletes the old bundle object.
- Explicitly not implemented:
  pending-review auto-withdraw, route ownership move, portal publish write route ownership, and
  full Java/Python repeated publish matrix.
- Acceptance focus:
  repeat direct Python publish succeeds for the same slug/version, only one version remains, old
  storage is deleted, and proxy publish write ownership remains Java.

Candidate routes:

- ClawHub `POST /api/v1/skills`
- Web skill publish/upload endpoints.
- Package validation endpoints or helpers needed by publish.

Bridge design required before implementation:

- Auth requirement from Group C.
- Multipart upload handling.
- Skill package extraction and validation parity.
- Object storage write path from Group B.
- Scanner API integration and failure behavior.
- Transaction boundary for skill/version/file records.
- Idempotency and duplicate publish behavior.

Acceptance focus:

- Publish a deterministic fixture package through Python.
- Java reference comparison where practical.
- DB rows, stored objects, scanner result, and frontend publish flow are verified.

### Group E. Skill Lifecycle And Governance Mutations

Goal:

- Move lifecycle state transitions and governance actions after auth, storage, and publish are
  available in Python.

Candidate routes:

- submit review / approve / reject / withdraw.
- confirm publish / rerelease.
- archive / unarchive.
- yank / hide / restore.
- delete / undelete / hard-delete if used internally.

Bridge design required before implementation:

- Namespace role checks and platform RBAC.
- Audit log behavior.
- Notification/event behavior.
- Idempotency behavior for repeated requests.
- Transaction and compensation behavior.

Acceptance focus:

- State transitions match `docs/14-skill-lifecycle.md`.
- Mutations are covered by unit, integration, and live workflow tests.
- Java remains a reference only; Python becomes workflow owner after passing the gate.

### Group F. Social, Ratings, Subscriptions, Notifications

Goal:

- Move viewer-specific interaction APIs after auth and lifecycle foundations are stable.

Candidate routes:

- star / unstar.
- rate.
- subscribe / unsubscribe.
- notification reads and SSE if needed for internal workflows.

Bridge design required before implementation:

- Auth context from Group C.
- Duplicate interaction behavior.
- Notification delivery expectations.
- Frontend state refresh behavior.

### Group G. Admin, Labels Mutation, Namespace, Tokens, OAuth

Goal:

- Move remaining protected administrative and platform-security routes after core internal flows are
  stable.

Candidate areas:

- Admin user management.
- Label creation/update/delete.
- Namespace management.
- API token management.
- OAuth flow if the organization still needs it.

Bridge design required before implementation:

- RBAC model.
- Internal identity provider decision.
- Token hashing/secret handling.
- Audit and recovery behavior.

### Group H. Post-Migration ORM Refactoring and Schema Takeover

Goal:

- Standardize Python data access after all endpoint groups have moved off Java.
- Replace raw SQL queries (`sqlalchemy.text`) in repositories with structured SQLAlchemy ORM models without changing database ownership in the same step.
- After the ORM swap is stable, transfer database schema migration ownership from Java Flyway to Python Alembic or an equivalent Python-native migration tool.

Target Areas:

Phase H1 - ORM data-access refactor:

- Define full SQLAlchemy ORM models mapping to all database tables (`skill`, `skill_version`, `skill_file`, `review_task`, `security_audit`, `label_definition`, `label_translation`, `user_account`, etc.).
- Convert repositories (`app/repositories/`) from `sqlalchemy.text` queries to SQLAlchemy ORM queries.
- Introduce session-based Unit of Work transaction boundaries where repository operations currently rely on ad hoc engine usage.
- Keep Java Flyway as the schema source of truth during this phase. Do not require Alembic for the ORM conversion itself.

Phase H2 - Python schema migration takeover:

- Set up Alembic or another Python-native schema migration tool only after the ORM repositories are stable.
- Baseline the existing Flyway-created database schema so the Python migration tool starts from the current production schema instead of trying to recreate it.
- From the baseline revision forward, write new schema changes in the Python migration tool.
- Clean up and remove Java Flyway migrations, configuration files, and references only after Java backend deprecation is finalized and the Python migration pipeline is verified in local, staging, and CI.

Bridge design required before implementation:

- H1 regression plan: ensure all automated integration/E2E tests remain green after the ORM repository swap.
- H1 performance benchmark check: verify that ORM relationship loading does not introduce N+1 query patterns.
- H2 migration plan: document the Flyway-to-Alembic baseline process, including how existing databases are stamped and how new databases are initialized.
- H2 environment integration: wire the Python migration command into local DB setup/teardown, staging, and CI before Flyway references are removed.

## Historical Endpoint Milestones

### 2. Public Labels Read API

Routes:

- `GET /api/v1/labels`
- `GET /api/web/labels`

Status:

- Completed. Keep this section for historical context and contract ownership.

Why next:

- Public and read-only.
- No auth/session/CSRF.
- First useful PostgreSQL read model.
- Establishes Python DB settings, SQLAlchemy/asyncpg, contract comparison, and locale fallback
  behavior before touching skill APIs.

Primary dependencies:

- PostgreSQL only.
- Tables: `label_definition`, `label_translation`.

Implementation plan:

- Existing draft:
  `docs/backend-python-migration/plans/2026-06-06-public-labels-api.md`
- Before implementation, review that plan and update dates/details if needed.

Acceptance focus:

- Match Java `SkillLabelDto` contract: `slug`, `type`, `displayName`.
- Match Java locale fallback: normalized full locale, language, `en`, then slug.
- Vite proxy routes both aliases to Python.
- No admin label endpoints are migrated.

### 3. Skill Labels List API

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/labels`
- `GET /api/web/skills/{namespace}/{slug}/labels`

Why after public labels:

- It is skill-adjacent but still a small read-only API.
- It can reuse label DTO, localization, and DB infrastructure from the public labels milestone.
- It introduces skill lookup and visibility rules before larger skill detail/search APIs.

Primary dependencies:

- PostgreSQL.
- Skill coordinate lookup by `{namespace}/{slug}`.
- Published/public visibility rules.
- Existing label tables plus skill-label join table.

Constraints:

- Do not migrate `PUT /labels/{labelSlug}`.
- Do not migrate `DELETE /labels/{labelSlug}`.
- Do not introduce lifecycle mutation logic.

Acceptance focus:

- Anonymous public behavior matches Java for published visible skills.
- If viewer-specific owner preview behavior is required by Java, document it before coding.
- Route aliases both behave identically.

Status:

- Completed for anonymous public behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-skill-labels-list-api.md`
- Auth-specific preview behavior remains deferred until the auth/session bridge is designed.

### 4. Public Skill Resolve API

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/resolve`
- `GET /api/web/skills/{namespace}/{slug}/resolve`

Why here:

- Smaller than full skill detail.
- Useful for CLI and install flows.
- Exercises version selectors without file streaming.

Primary dependencies:

- PostgreSQL.
- Skill coordinate lookup.
- Version selector handling: `version`, `tag`, `hash`.
- Published version resolution.

Constraints:

- Do not stream files.
- Do not increment download counters.
- Do not handle object storage.
- Do not migrate download endpoints in this milestone.

Acceptance focus:

- Match Java `ResolveVersionResponse`.
- `latest` tag follows latest published version only.
- Unpublished/yanked versions are not exposed to anonymous public callers.

Status:

- Completed for anonymous public behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-resolve-api.md`
- Auth-specific preview behavior and download execution remain deferred until their bridge designs
  are written.

### 5. Public Skill Version List

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/versions`
- `GET /api/web/skills/{namespace}/{slug}/versions`

Why after resolve:

- Builds on published version resolution.
- Still read-only and no object storage.
- Prepares for skill detail and file metadata.

Primary dependencies:

- PostgreSQL.
- Pagination.
- Published version filtering.
- Java-compatible `PageResponse<SkillVersionResponse>`.

Constraints:

- Do not expose owner preview versions until auth/role bridge is designed.
- Do not migrate version detail in this milestone.
- Do not migrate file content or download endpoints.

Acceptance focus:

- Match Java page envelope and version DTOs.
- Confirm behavior for anonymous public caller first.
- Add viewer-specific behavior only after explicit design.

Status:

- Completed for anonymous public behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-versions-list-api.md`
- Auth-specific manager-visible non-published versions remain deferred until the auth/session bridge
  is designed.

### 5.1. Public Skill Version Detail

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`

Why after version list:

- Builds on public skill lookup and published version filtering.
- Adds metadata JSON and manifest JSON fields without file bytes or object storage.

Primary dependencies:

- PostgreSQL.
- Exact published version lookup.
- Metadata JSON / manifest JSON fields.

Constraints:

- Do not expose owner preview versions until auth/role bridge is designed.
- Do not migrate file list, file content, compare, or download routes.

Acceptance focus:

- Match Java `SkillVersionDetailResponse`.
- Confirm anonymous public behavior before any auth-specific behavior.

Status:

- Completed for anonymous public behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-version-detail-api.md`
- Auth-specific owner/admin preview for non-published versions remains deferred until the
  auth/session bridge is designed.

### 6. Public Skill File Metadata

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files`

Why here:

- Read-only metadata, not file bytes.
- Uses version/tag resolution from earlier milestones.

Primary dependencies:

- PostgreSQL.
- Skill file metadata table.
- Published version visibility.

Constraints:

- Do not migrate `file?path=...`.
- Do not access MinIO/S3/local object storage.

Acceptance focus:

- Match Java `SkillFileResponse`: `id`, `filePath`, `fileSize`, `contentType`, `sha256`.
- Ensure path ordering matches Java.

### 7. Public Skill Detail

Routes:

- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`

Why later:

- This is the first larger skill read model.
- It combines skill core fields, lifecycle projection, labels, permissions, rating/star counts, and
  viewer capabilities.

Primary dependencies:

- PostgreSQL.
- Skill, namespace, owner display, latest published version, labels, social counts.
- Lifecycle projection rules.

Constraints:

- Start with anonymous/public behavior only unless auth bridge is already designed.
- Do not claim owner preview parity until namespace roles are bridged.
- Do not migrate lifecycle mutation endpoints with detail.

Acceptance focus:

- Public browsing uses published version only.
- `hidden=true`, archived, yanked, and no-published-version cases match Java.
- Capability flags are explicitly documented for anonymous and authenticated callers.

Status:

- Completed for anonymous public behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md`
- Authenticated owner/admin preview, namespace role checks, lifecycle permissions, and viewer state
  remain deferred until the auth/session bridge is designed.

### 8. Public Portal Skill Search

Routes:

- `GET /api/web/skills`

Why after detail:

- Search/filter/pagination has broader read-model and performance risk.
- It may depend on PostgreSQL full-text behavior and labels.

Primary dependencies:

- PostgreSQL full-text search or equivalent query.
- Labels, namespace, lifecycle visibility.
- Pagination and sorting.

Constraints:

- Do not migrate `GET /api/v1/skills`; that route is ClawHub compatibility list and remains
  Java-owned.
- Do not migrate `POST /api/v1/skills`; that route is ClawHub compatibility publish and remains
  Java-owned.
- Do not introduce a new search engine.
- Do not change ranking semantics without explicit product approval.

Acceptance focus:

- Match Java query parameters and page response.
- Compare representative search/filter fixtures against Java.

Status:

- Completed for anonymous public portal behavior.
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md`
- `GET /api/v1/skills` remains Java-owned because it is ClawHub compatibility list/publish, not
  portal search.

## High-Dependency Notes From The Original Plan

These notes explain why later groups need bridge designs before implementation. They are no longer
the migration order; the active order is `Revised Pre-Launch Milestone Order` above.

### Download and File Content

Deferred routes:

- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`

Reason:

- Requires object storage, stream/redirect behavior, download metrics, rate limiting, and fallback
  bundle handling.

### Mutating Skill Lifecycle

Deferred routes:

- publish
- submit review
- confirm publish
- archive / unarchive
- delete
- withdraw review
- rerelease
- yank / hide / restore admin governance

Reason:

- Requires lifecycle transition parity, transactions, events, permissions, audit logs, object
  storage compensation, scanner integration, and CSRF/session handling.

### Social Mutations and Viewer State

Deferred routes:

- star / unstar
- rate
- subscribe / unsubscribe

Reason:

- Mutations require auth/session and CSRF design.
- Read-only viewer state can be considered only after auth principal bridging exists.

### Auth, OAuth, Session, API Tokens

Deferred routes:

- `/api/v1/auth/**`
- `/oauth2/**`
- bearer-token authentication filters and scope enforcement

Reason:

- These are platform security boundaries and should be designed as a separate bridge.

## Environment Notes

Windows and macOS:

- Use Docker-managed dependency services for local development and E2E.

Ubuntu:

- Do not use Docker-managed PostgreSQL/Redis/MinIO.
- Developers manually adjust
  `server/skillhub-app/src/main/resources/application-local.yml` locally to point Java at
  organization services.
- Python uses its own environment variables and must not read Java YAML directly.

## Update Rules For This File

When this plan changes:

- Record why the order changed.
- Keep completed milestones immutable except for adding result links.
- Move only the smallest reasonable API group at a time.
- Keep deferred groups deferred unless a milestone-specific bridge design exists.
- Commit the plan update before implementation begins.

## Current Next Step

Group A public catalog read ownership is complete. Group B file content/download read path is
complete. Group C has the local current-user bridge and viewer-specific read assumptions needed for
the current pre-launch publish work. Group D publish foundations are complete through root,
legacy, CLI, and portal publish write ownership plus scanner result application and daemon runtime:

- `POST /api/cli/v1/skills/{namespace}/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/v1/skills`
- `POST /api/v1/publish`
- normalized scanner result -> `security_audit` update and `SCANNING` status transition
- Java-compatible Redis scan task field parsing and one-task Python worker boundary
- Redis consumer group runtime with one-pass consume/reclaim, ACK, and retry republish semantics
- scanner HTTP client for real scanner service upload/local mode response mapping
- FastAPI-managed background scan daemon/supervisor lifecycle

Group E has started with review lifecycle write ownership:

- Completed: `POST /api/v1/reviews/{id}/approve` and
  `POST /api/web/reviews/{id}/approve`.
- Completed: `POST /api/v1/reviews/{id}/reject`,
  `POST /api/web/reviews/{id}/reject`, `POST /api/v1/reviews/{id}/withdraw`, and
  `POST /api/web/reviews/{id}/withdraw`.
- Completed: `POST /api/v1/reviews` and `POST /api/web/reviews`.
- Completed: `GET /api/v1/reviews`, `GET /api/web/reviews`,
  `GET /api/v1/reviews/pending`, `GET /api/web/reviews/pending`,
  `GET /api/v1/reviews/my-submissions`, and `GET /api/web/reviews/my-submissions`.
- Completed: `GET /api/v1/reviews/{id}` and `GET /api/web/reviews/{id}`.
- Completed: `GET /api/v1/reviews/{id}/skill-detail` and
  `GET /api/web/reviews/{id}/skill-detail`.
- Completed: `GET /api/v1/reviews/{id}/file` and
  `GET /api/web/reviews/{id}/file`.
- Completed: `GET /api/v1/reviews/{id}/download` and
  `GET /api/web/reviews/{id}/download`.
- Completed: promotion read APIs:
  `GET /api/v1/promotions`, `GET /api/web/promotions`,
  `GET /api/v1/promotions/pending`, `GET /api/web/promotions/pending`,
  `GET /api/v1/promotions/{id}`, and `GET /api/web/promotions/{id}`.
- Completed: promotion submit/reject APIs:
  `POST /api/v1/promotions`, `POST /api/web/promotions`,
  `POST /api/v1/promotions/{id}/reject`, and
  `POST /api/web/promotions/{id}/reject`.
- Completed: promotion approve APIs:
  `POST /api/v1/promotions/{id}/approve` and
  `POST /api/web/promotions/{id}/approve`.
- Completed: portal skill archive/unarchive APIs:
  `POST /api/v1/skills/{namespace}/{slug}/archive`,
  `POST /api/web/skills/{namespace}/{slug}/archive`,
  `POST /api/v1/skills/{namespace}/{slug}/unarchive`, and
  `POST /api/web/skills/{namespace}/{slug}/unarchive`.
- Completed: portal version delete APIs:
  `DELETE /api/v1/skills/{namespace}/{slug}/versions/{version}` and
  `DELETE /api/web/skills/{namespace}/{slug}/versions/{version}`.
- Completed: portal version withdraw-review APIs:
  `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review` and
  `POST /api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review`.
- Completed: portal confirm-publish APIs:
  `POST /api/v1/skills/{namespace}/{slug}/confirm-publish` and
  `POST /api/web/skills/{namespace}/{slug}/confirm-publish`.
- Completed: portal submit-review APIs:
  `POST /api/v1/skills/{namespace}/{slug}/submit-review` and
  `POST /api/web/skills/{namespace}/{slug}/submit-review`.
- Completed: portal rerelease APIs:
  `POST /api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease` and
  `POST /api/web/skills/{namespace}/{slug}/versions/{version}/rerelease`.
- Completed: platform-admin skill hide/unhide APIs:
  `POST /api/v1/admin/skills/{skillId}/hide` and
  `POST /api/v1/admin/skills/{skillId}/unhide`.
- Completed: admin version yank API:
  `POST /api/v1/admin/skills/versions/{versionId}/yank`.
- Completed: notification read/read-state APIs:
  `GET /api/v1/notifications`, `GET /api/web/notifications`,
  `GET /api/v1/notifications/unread-count`, `GET /api/web/notifications/unread-count`,
  `PUT /api/v1/notifications/{id}/read`, `PUT /api/web/notifications/{id}/read`,
  `PUT /api/v1/notifications/read-all`, `PUT /api/web/notifications/read-all`,
  `DELETE /api/v1/notifications/{id}`, and `DELETE /api/web/notifications/{id}`.
- Completed: notification preference APIs:
  `GET /api/v1/notification-preferences`, `GET /api/web/notification-preferences`,
  `PUT /api/v1/notification-preferences`, and `PUT /api/web/notification-preferences`.
- Completed: notification SSE connection boundary APIs:
  `GET /api/v1/notifications/sse` and `GET /api/web/notifications/sse`. These move the
  event-stream connection route to Python, preserve authentication rejection, `connected` event,
  and heartbeat comment shape, and defer active notification fanout until Python has a unified
  notification dispatcher abstraction.
- Completed: current-user owned skill list APIs:
  `GET /api/v1/me/skills` and `GET /api/web/me/skills`.
- Completed: namespace read APIs:
  `GET /api/v1/namespaces`, `GET /api/web/namespaces`,
  `GET /api/v1/me/namespaces`, `GET /api/web/me/namespaces`,
  `GET /api/v1/namespaces/{slug}`, and `GET /api/web/namespaces/{slug}`.
- Completed: namespace member read APIs:
  `GET /api/v1/namespaces/{slug}/members`, `GET /api/web/namespaces/{slug}/members`,
  `GET /api/v1/namespaces/{slug}/member-candidates`, and
  `GET /api/web/namespaces/{slug}/member-candidates`.
- Completed: namespace member mutation APIs:
  `POST /api/v1/namespaces/{slug}/members`, `POST /api/web/namespaces/{slug}/members`,
  `DELETE /api/v1/namespaces/{slug}/members/{userId}`,
  `DELETE /api/web/namespaces/{slug}/members/{userId}`,
  `PUT /api/v1/namespaces/{slug}/members/{userId}/role`,
  `PUT /api/web/namespaces/{slug}/members/{userId}/role`,
  `POST /api/v1/namespaces/{slug}/members/batch`, and
  `POST /api/web/namespaces/{slug}/members/batch`.
- Completed: namespace ownership transfer APIs:
  `POST /api/v1/namespaces/{slug}/transfer-ownership` and
  `POST /api/web/namespaces/{slug}/transfer-ownership`.
- Completed: namespace profile/lifecycle mutation APIs:
  `POST /api/v1/namespaces`, `POST /api/web/namespaces`,
  `PUT /api/v1/namespaces/{slug}`, `PUT /api/web/namespaces/{slug}`,
  `DELETE /api/v1/namespaces/{slug}`, `DELETE /api/web/namespaces/{slug}`,
  `POST /api/v1/namespaces/{slug}/freeze`, `POST /api/web/namespaces/{slug}/freeze`,
  `POST /api/v1/namespaces/{slug}/unfreeze`, `POST /api/web/namespaces/{slug}/unfreeze`,
  `POST /api/v1/namespaces/{slug}/archive`, `POST /api/web/namespaces/{slug}/archive`,
  `POST /api/v1/namespaces/{slug}/restore`, and
  `POST /api/web/namespaces/{slug}/restore`.
- Completed: admin label definition APIs:
  `GET /api/v1/admin/labels`, `POST /api/v1/admin/labels`,
  `PUT /api/v1/admin/labels/{slug}`, `DELETE /api/v1/admin/labels/{slug}`, and
  `PUT /api/v1/admin/labels/sort-order`. Skill label attach/detach remains Java-owned.
- Completed: admin user management basic APIs:
  `GET /api/v1/admin/users`, `PUT /api/v1/admin/users/{userId}/role`,
  `PUT /api/v1/admin/users/{userId}/status`,
  `POST /api/v1/admin/users/{userId}/approve`,
  `POST /api/v1/admin/users/{userId}/disable`, and
  `POST /api/v1/admin/users/{userId}/enable`.
- Completed: admin password reset trigger API:
  `POST /api/v1/admin/users/{userId}/password-reset`. The route now writes Java-compatible
  BCrypt reset request rows and keeps local register/login/change-password routes Java-owned.
- Completed: API token management APIs:
  `POST /api/v1/tokens`, `GET /api/v1/tokens`, `DELETE /api/v1/tokens/{id}`, and
  `PUT /api/v1/tokens/{id}/expiration`. These move self-service token CRUD/storage behavior
  to Python. Current-principal bearer-token reads now work in Python, and these token management
  routes now enforce Java-compatible bearer `token:manage` scope. Broader route-policy scope
  enforcement and OAuth remain deferred.
- Completed: anonymous local password reset APIs:
  `POST /api/v1/auth/local/password-reset/request` and
  `POST /api/v1/auth/local/password-reset/confirm`. These move reset code creation and password
  reset confirmation to Python while keeping local register/login/change-password, OAuth, session
  bootstrap, bearer-token authentication, and scope enforcement Java-owned.
- Completed: local auth core APIs:
  `POST /api/v1/auth/local/register`, `POST /api/v1/auth/local/login`, and
  `POST /api/v1/auth/local/change-password`. These move local account creation, password login,
  and password change to Python while preserving Java credential/password-policy/lockout DB
  behavior. Spring Session creation remains deferred to the final auth/session replacement work.
- Completed: public auth catalog read APIs:
  `GET /api/v1/auth/providers` and `GET /api/v1/auth/methods`. These move provider/method
  discovery to Python while keeping OAuth callbacks/authorization, bearer-token authentication,
  and scope enforcement Java-owned.
- Completed: direct/session auth boundary APIs:
  `POST /api/v1/auth/direct/login` and `POST /api/v1/auth/session/bootstrap`. These move the
  default-disabled route boundary to Python, preserve Java 403 disabled behavior and
  unsupported-provider ordering, and keep final cookie/session persistence, passive bootstrap
  success, bearer-token authentication, and scope enforcement deferred.
- Completed: current-principal whoami read APIs:
  `GET /api/v1/whoami` and `GET /api/cli/v1/auth/whoami`. These move ClawHub and CLI
  whoami reads to Python. They now accept mock-user or bearer-token principals while keeping OAuth
  callbacks/authorization and global scope enforcement deferred.
- Completed: current-user profile APIs:
  `GET /api/v1/user/profile` and `PATCH /api/v1/user/profile`. These move the self-service
  profile read/update boundary to Python, preserving Java display-name validation, latest
  PENDING/REJECTED change request projection, PENDING self-view overlay, default human-review
  queueing, and immediate-apply audit behavior. Spring Session refresh remains deferred to final
  session replacement.
- Completed: security audit read API:
  `GET /api/v1/skills/{skillId}/versions/{versionId}/security-audit`. This moves the
  authenticated audit read boundary to Python, preserving Java version/skill mismatch handling,
  visibility checks, latest active audit selection per scanner type, optional `scannerType`,
  empty-list response for versions without audits, and Java response envelope.
- Completed: governance workbench read APIs:
  `GET /api/v1/governance/summary`, `GET /api/web/governance/summary`,
  `GET /api/v1/governance/inbox`, `GET /api/web/governance/inbox`,
  `GET /api/v1/governance/activity`, `GET /api/web/governance/activity`,
  `GET /api/v1/governance/notifications`, and `GET /api/web/governance/notifications`.
  Legacy governance notification mark-read has also moved to Python.
- Completed: admin audit log read API:
  `GET /api/v1/admin/audit-logs`.
- Completed: admin report/review list read APIs:
  `GET /api/v1/admin/skill-reports` and `GET /api/v1/admin/profile-reviews`.
  Skill report resolve/dismiss and profile review approve/reject are now also Python-owned.
- Completed: admin report/profile review mutation APIs:
  `POST /api/v1/admin/skill-reports/{reportId}/resolve`,
  `POST /api/v1/admin/skill-reports/{reportId}/dismiss`,
  `POST /api/v1/admin/profile-reviews/{id}/approve`, and
  `POST /api/v1/admin/profile-reviews/{id}/reject`.
  Live gate caught and fixed two parity details: profile review `reviewed_at` must use DB-compatible
  timestamp binding, and `HIDE_SKILL` audit reason preserves the raw Java comment while
  `skill_report.handle_comment` stores the trimmed comment.
- Completed: skill report submit APIs:
  `POST /api/v1/skills/{namespace}/{slug}/reports` and
  `POST /api/web/skills/{namespace}/{slug}/reports`. These move the user-facing report
  submission path to Python with Java-compatible published-preference target resolution,
  blank/self/duplicate/unavailable validation, `REPORT_SKILL` audit, and `REPORT_SUBMITTED`
  notification side effects.
- Completed: skill label attach/detach APIs:
  `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`,
  `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`,
  `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`, and
  `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`.
  These close the skill-label mutation gap after admin label definitions and label reads moved to Python.
- Completed: skill tag management APIs:
  `GET /api/v1/skills/{namespace}/{slug}/tags`,
  `GET /api/web/skills/{namespace}/{slug}/tags`,
  `PUT /api/v1/skills/{namespace}/{slug}/tags/{tagName}`,
  `PUT /api/web/skills/{namespace}/{slug}/tags/{tagName}`,
  `DELETE /api/v1/skills/{namespace}/{slug}/tags/{tagName}`, and
  `DELETE /api/web/skills/{namespace}/{slug}/tags/{tagName}`.
  Live gate caught and fixed one parity detail: tag management success messages must use the
  live Java localized messages (`获取成功`, `更新成功`, `删除成功`) instead of raw message keys.
- Completed: legacy governance notification mark-read APIs:
  `POST /api/v1/governance/notifications/{id}/read` and
  `POST /api/web/governance/notifications/{id}/read`.
  Live gate caught and fixed a Python transaction boundary issue: the route response showed
  `READ`, but the DB state stayed `UNREAD` until the mutation used `engine.begin()`.
- Completed: web download alias APIs:
  `GET /api/web/skills/{namespace}/{slug}/download`,
  `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`, and
  `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download`.
  These share the existing Python v1 download implementation. Live gate now compares Java/Python/proxy
  web alias stream contracts and verifies published download counter deltas across v1 and web hits.
- Completed: whole-skill hard-delete APIs:
  `DELETE /api/v1/skills/id/{skillId}`,
  `DELETE /api/v1/skills/{namespace}/{slug}`,
  `DELETE /api/web/skills/id/{skillId}`, and
  `DELETE /api/web/skills/{namespace}/{slug}`.
  Live gate compares Java/Python/proxy delete envelopes and DB/storage side effects, including
  search document removal, version/file/security cleanup, `DELETE_SKILL_HARD` audit, local storage
  deletion, and ClawHub delete/undelete Java-owned boundary preservation. The live fixture also
  caught one Java enum compatibility issue: `security_audit.scanner_type` fixture rows must use
  `SKILL_SCANNER` so Java JPA can read them.
- Still Java-owned/deferred: broader post-publish lifecycle/governance actions outside the migrated
  portal review/promotion/skill lifecycle and admin skill governance routes, auth/OAuth
  surfaces outside migrated current-user/token/local-auth/password-reset/direct-session/account-merge
  device-auth, and bearer current-principal boundary routes, Spring Session establishment,
  global bearer-token scope enforcement, active SSE notification fanout, and final proxy cleanup.

Recommended next choice:

- Continue with remaining auth/session/global bearer-scope surfaces or final proxy cleanup based on
  route ownership priority.

Every next choice must include route-specific live gates and must keep `server/` read-only.

Recently completed context:

The public skill detail milestone is complete for anonymous public behavior:

- Plan:
  `docs/backend-python-migration/plans/2026-06-07-public-skill-detail-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-detail-api.md`

The public portal skill search milestone is complete for anonymous public behavior:

`GET /api/web/skills`

- Plan:
  `docs/backend-python-migration/plans/2026-06-07-public-skill-search-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-07-public-skill-search-api.md`

The ClawHub compatibility search milestone is complete:

- Route:
  `GET /api/v1/search`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-clawhub-search-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-clawhub-search-api.md`

The ClawHub compatibility resolve milestone is complete:

- Routes:
  `GET /api/v1/resolve`, `GET /api/v1/resolve/{canonicalSlug}`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-clawhub-resolve-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-clawhub-resolve-api.md`

The method-aware Vite proxy infrastructure milestone is complete:

- Plan:
  `docs/backend-python-migration/plans/2026-06-08-method-aware-vite-proxy.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-method-aware-vite-proxy.md`

The ClawHub skill detail milestone is complete:

- Route:
  `GET /api/v1/skills/{canonicalSlug}`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-clawhub-skill-detail-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-clawhub-skill-detail-api.md`

The ClawHub skills list milestone is complete:

- Route:
  `GET /api/v1/skills`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-clawhub-skills-list-api.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-clawhub-skills-list-api.md`

The auth current-user bridge milestone is complete:

- Route:
  `GET /api/v1/auth/me`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-auth-current-user-bridge.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-auth-current-user-bridge.md`

The authenticated skill detail capabilities milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}`, `GET /api/web/skills/{namespace}/{slug}`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-authenticated-skill-detail-capabilities.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-authenticated-skill-detail-capabilities.md`

The skill detail owner preview milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}`, `GET /api/web/skills/{namespace}/{slug}`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-skill-detail-owner-preview.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-skill-detail-owner-preview.md`

The owner preview version read milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/versions`,
  `GET /api/web/skills/{namespace}/{slug}/versions`,
  `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`,
  `GET /api/web/skills/{namespace}/{slug}/versions/{version}`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-owner-preview-version-read.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-owner-preview-version-read.md`

The owner preview file metadata milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/files`,
  `GET /api/web/skills/{namespace}/{slug}/versions/{version}/files`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-owner-preview-file-metadata.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-owner-preview-file-metadata.md`

The owner preview resolve parity milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/resolve`,
  `GET /api/web/skills/{namespace}/{slug}/resolve`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-owner-preview-resolve.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-owner-preview-resolve.md`

The owner preview version compare milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/versions/compare`,
  `GET /api/web/skills/{namespace}/{slug}/versions/compare`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-owner-preview-version-compare.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-owner-preview-version-compare.md`

The owner preview tag files parity milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/files`,
  `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/files`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-owner-preview-tag-files.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-owner-preview-tag-files.md`

The file content read foundation milestone is complete:

- Routes:
  `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`,
  `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`
- Plan:
  `docs/backend-python-migration/plans/2026-06-08-file-content-read-foundation.md`
- Result:
  `docs/backend-python-migration/results/2026-06-08-file-content-read-foundation.md`
