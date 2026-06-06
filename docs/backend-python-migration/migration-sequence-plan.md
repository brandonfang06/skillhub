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
6. Run verification.
7. Confirm `git diff --name-only -- server` returns no paths.
8. Commit and push to `dev`.

If priorities change, update this file first, then continue from the revised order.

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

## Planned Migration Order

### 2. Public Labels Read API

Routes:

- `GET /api/v1/labels`
- `GET /api/web/labels`

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

### 5. Public Skill Version List and Version Detail

Routes:

- `GET /api/v1/skills/{namespace}/{slug}/versions`
- `GET /api/web/skills/{namespace}/{slug}/versions`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`

Why after resolve:

- Builds on published version resolution.
- Still read-only and no object storage.
- Prepares for skill detail and file metadata.

Primary dependencies:

- PostgreSQL.
- Pagination.
- Published version filtering.
- Metadata JSON / manifest JSON fields.

Constraints:

- Do not expose owner preview versions until auth/role bridge is designed.
- Do not migrate file content or download endpoints.

Acceptance focus:

- Match Java page envelope and version DTOs.
- Confirm behavior for anonymous public caller first.
- Add viewer-specific behavior only after explicit design.

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

### 8. Public Skill Search

Routes:

- `GET /api/v1/skills`
- `GET /api/web/skills`

Why after detail:

- Search/filter/pagination has broader read-model and performance risk.
- It may depend on PostgreSQL full-text behavior and labels.

Primary dependencies:

- PostgreSQL full-text search or equivalent query.
- Labels, namespace, lifecycle visibility.
- Pagination and sorting.

Constraints:

- Do not introduce a new search engine.
- Do not change ranking semantics without explicit product approval.

Acceptance focus:

- Match Java query parameters and page response.
- Compare representative search/filter fixtures against Java.

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

The next implementation milestone should be:

`GET /api/v1/labels` and `GET /api/web/labels`

Before implementation starts:

- Review and update `docs/backend-python-migration/plans/2026-06-06-public-labels-api.md`.
- Confirm the exact database URL strategy for Windows/macOS Docker and Ubuntu organization
  PostgreSQL.
- Announce the API boundary, allowed files, and acceptance criteria.
