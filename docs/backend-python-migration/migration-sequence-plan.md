# Backend Python Migration Sequence Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:writing-plans` when changing this
> sequence, and use `superpowers:executing-plans` when implementing an approved milestone. This is
> the living migration order document; update this file whenever priorities change.

**Goal:** Maintain the agreed migration order for moving SkillHub backend APIs from Java to
FastAPI while Java and Python coexist.

**Architecture:** Migration proceeds from low-dependency public read APIs toward database-backed
read models, then viewer-specific skill reads, then storage/search/auth/mutation workflows. Java
under `server/` remains read-only throughout migration; Python-owned routes live under
`server-python/` and are routed by Vite dev proxy during coexistence.

**Tech Stack:** Spring Boot Java backend as read-only reference, FastAPI Python backend on port
`8081`, Vite dev proxy on port `3000`, Java backend on port `8080`, PostgreSQL introduced only
after no-DB routes are stable.

---

## How To Use This Plan

This file is the source of truth for migration order. For every milestone:

1. Announce the selected API or API group before changing files.
2. Create or update a milestone-specific plan under
   `docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md`.
3. Implement with TDD.
4. Update `docs/backend-python-migration/route-registry.md` when ownership changes.
5. Write a result document under `docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md`.
6. Run unit/proxy verification.
7. Run the live verification gate before starting the next API migration.
8. Confirm `git diff --name-only -- server` returns no paths.
9. Commit and push to `dev`.

If priorities change, update this file first, then continue from the revised order.

## Live Verification Gate

Every API migration must pass a live verification gate before the next API migration starts. This
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
- Do not begin the next API migration until this gate has passed or the project owner explicitly
  accepts a recorded blocker.

## Non-Negotiable Boundaries

- Do not modify any file under `server/`.
- Do not edit Java config, migrations, controllers, services, tests, generated DTOs, or resources.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not migrate auth, session, OAuth, CSRF, API token, idempotency, publish, lifecycle mutation,
  storage download, or admin mutation APIs until their bridge designs are explicitly planned.
- Keep route ownership small and explicit. One milestone should own one API or a small alias group.

## Selection Criteria

Prefer earlier APIs when they are:

- Public or anonymous-readable.
- GET-only.
- Easy to compare against Java with `curl`.
- Low dependency: no auth/session, no object storage, no Redis, no MinIO, no mutation.
- Useful for establishing reusable Python infrastructure.

Defer APIs when they require:

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
| 10 | `GET /api/v1/resolve`, `GET /api/v1/resolve/{canonicalSlug}` | python | ClawHub compatibility resolve migrated. Download and ClawHub skill detail remain Java-owned. |

## Planned Migration Order

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

## Deferred High-Dependency Groups

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

The next API milestone should be selected with a new plan. Current notes:

- `GET /api/v1/skills/{canonicalSlug}` is a possible ClawHub compatibility candidate, but must be
  planned separately because it shares the `/api/v1/skills/**` namespace with Java-owned delete,
  undelete, publish, and existing public nested SkillHub routes.
- Do not migrate `GET /api/v1/skills` without a separate ClawHub compatibility plan and a
  method-aware routing decision; the same path also owns `POST /api/v1/skills`.
- Do not migrate download routes until object storage and redirect/download metrics behavior have
  a separate bridge plan.
- Keep all mutating, auth-specific, lifecycle, and download routes Java-owned until their bridge
  designs are written.
