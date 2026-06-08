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
`8081`, Vite dev proxy on port `3000`, Java backend on port `8080`, PostgreSQL introduced only
after no-DB routes are stable.

---

## How To Use This Plan

This file is the source of truth for migration order. For every milestone:

1. Announce the selected API, API group, or workflow before changing files.
2. Create or update a milestone-specific plan under
   `docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md`.
3. Implement with TDD.
4. Update `docs/backend-python-migration/route-registry.md` when ownership changes.
5. Write a result document under `docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md`.
6. Run unit/proxy verification.
7. Run the live verification gate before starting the next migration group.
8. Confirm `git diff --name-only -- server` returns no paths.
9. Commit and push to `dev`.

If priorities change, update this file first, then continue from the revised order.

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

Remaining candidate in this group:

- None after the ClawHub list milestone completes and its result is committed.

Keep Java-owned in this group:

- `POST /api/v1/skills`
- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- all download/file-content routes.

Acceptance focus:

- `GET /api/v1/skills` plain ClawHub list matches Java.
- Root `POST /api/v1/skills` still reaches Java until publish/upload is planned.
- Existing Python read routes stay green.
- Vite proxy rules become simpler where possible, but method collisions remain explicitly tested.

### Group B. File Content And Download Read Path

Goal:

- Move public file content and download routes to Python as one storage/read workflow.

Candidate routes:

- `GET /api/v1/download/{canonicalSlug}`
- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`

Bridge design required before implementation:

- Object storage abstraction for Python: local file, MinIO/S3-compatible behavior.
- Redirect vs stream behavior and headers.
- Download counter behavior.
- Rate-limit assumptions.
- Missing object fallback behavior.
- Live fixture including stored file bytes.

Acceptance focus:

- Java/Python/Vite contract comparison for headers, status, redirects, and file bytes.
- No schema change under Python unless explicitly planned.
- Download metrics behavior is documented and tested.

### Group C. Auth And Current User Bridge

Goal:

- Establish the minimum Python auth/session model required for internal use before migrating
  viewer-specific reads or mutations.

Python-owned in this group:

- `GET /api/v1/auth/me`
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

Still Java-owned in this group:

- `GET /api/v1/auth/methods`
- `GET /api/v1/auth/providers`
- `POST /api/v1/auth/session/bootstrap`
- `POST /api/v1/auth/direct/login`
- `/api/v1/auth/local/**`
- `/api/v1/tokens/**`
- `/oauth2/**`
- `GET /api/v1/whoami`
- `GET /api/cli/v1/auth/whoami`

Next candidate routes:

- Namespace/platform role resolution helpers needed by protected frontend workflows.
- Local session-aware request context if internal development needs cookie-based web login before
  publish/upload migration.
- Viewer-specific list/search capability flags if the frontend needs them before publish/upload.
- Owner-preview access for resolve, tag file metadata, or download routes if the frontend needs
  those before publish/upload.

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
- OAuth/device flow if the organization still needs it.

Bridge design required before implementation:

- RBAC model.
- Internal identity provider decision.
- Token hashing/secret handling.
- Audit and recovery behavior.

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
- CLI auth/device flow
- API token management

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

Group A public catalog read ownership is complete after the ClawHub list milestone.

Group C has started with the narrow `GET /api/v1/auth/me` current-user bridge. The next milestone
choice should be one of:

- Continue Group C into viewer-specific read context and role helpers, if the priority is protected
  frontend workflows and later mutations.
- Start Group B file content and download read path, if the priority is install/download parity and
  object storage handling.

Do not start Group D publish/upload until Group B storage/download and Group C auth assumptions are
planned or explicitly scoped.

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
