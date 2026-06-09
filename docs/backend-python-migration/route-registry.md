# Backend Route Registry

This registry is the human-readable source of truth for Java/Python route
ownership during backend migration. Vite proxy config must stay in sync with
Python-owned local development routes.

The project is pre-launch, so future ownership changes may happen by cohesive
API group instead of one endpoint at a time. When a group moves, keep this table
explicit enough that Java-owned mutations, auth, OAuth, and other
deferred routes are still visible.

## Ownership Legend

| Owner | Meaning |
| --- | --- |
| `java` | Active implementation is the existing Spring Boot backend on port 8080. |
| `python` | Active implementation is the FastAPI backend on port 8081. |
| `planned-python` | Planned for Python, but not active until tests and proxy changes land. |

## Routes

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/.well-known/clawhub.json` | python | ClawHub compatibility discovery metadata. No DB/auth dependency. |
| GET | `/api/v1/health` | python | First milestone route. Mirrors Java `data.message = "UP"` envelope. |
| GET | `/api/v1/labels` | python | Public visible label filters. First PostgreSQL-backed Python route. |
| GET | `/api/web/labels` | python | Frontend alias for public visible label filters. |
| GET | `/api/v1/search` | python | ClawHub compatibility search. Plain ClawHub response, not `ApiResponse`. |
| GET | `/api/v1/resolve` | python | ClawHub compatibility resolve by query slug. Plain ClawHub response, not `ApiResponse`. |
| GET | `/api/v1/resolve/{canonicalSlug}` | python | ClawHub compatibility resolve by canonical slug. |
| GET | `/api/v1/download` | python | ClawHub compatibility download query route. Returns Java-compatible `302` redirect to portal v1 download route. |
| GET | `/api/v1/download/{canonicalSlug}` | python | ClawHub compatibility download path route. Returns Java-compatible `302` redirect to portal v1 download route. |
| GET | `/api/v1/auth/me` | python | Current local mock-user bridge for frontend auth context. Login, OAuth, token, and CLI auth remain Java-owned. |
| GET | `/api/v1/skills` | python | ClawHub compatibility list. Static exact-path proxy also carries root publish `POST /api/v1/skills`; canonical skill mutations remain Java-owned. |
| POST | `/api/v1/skills` | python | ClawHub compatibility publish moved to Python. Accepts Java-compatible `payload` JSON plus repeated `files` parts and returns plain `{ ok, skillId, versionId }`. |
| POST | `/api/v1/publish` | python | Legacy ClawHub compatibility publish moved to Python. Accepts multipart zip `file` plus `namespace` and returns plain `{ ok, skillId, versionId }`. |
| GET | `/api/v1/skills/{canonicalSlug}` | python | ClawHub compatibility skill detail. GET-only method-aware proxy; publish, delete, and undelete remain Java-owned. |
| GET | `/api/web/skills` | python | Public portal skill search. `/api/v1/skills` remains Java-owned ClawHub compatibility. |
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | python | Public anonymous skill labels list. Label mutations remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | python | Frontend alias for public anonymous skill labels list. Label mutations remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}` | python | Public skill detail with local mock-user viewer capability flags and manager-only owner preview projection. Non-public visibility and mutations remain deferred. |
| GET | `/api/web/skills/{namespace}/{slug}` | python | Frontend alias for public skill detail with local mock-user viewer capability flags and manager-only owner preview projection. Non-public visibility and mutations remain deferred. |
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | python | Public published version selector resolution with authenticated context forwarding. Non-published owner-preview resolve remains rejected to match Java. |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | python | Frontend alias for public published version selector resolution with authenticated context forwarding. Non-published owner-preview resolve remains rejected to match Java. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions` | python | Public published version list with manager-only owner preview lifecycle versions. Files metadata, compare, file bytes, and v1 downloads are Python-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/versions` | python | Frontend alias for public published version list with manager-only owner preview lifecycle versions. Files metadata and compare are Python-owned; web download aliases remain Java-owned/unmigrated. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/compare` | python | Public published version compare with manager-only owner preview access. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/compare` | python | Frontend alias for public published version compare with manager-only owner preview access. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | python | Public published version detail with manager-only non-published owner preview access. Files metadata, compare, file bytes, and v1 downloads are Python-owned; DELETE remains Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}` | python | Frontend alias for public published version detail with manager-only non-published owner preview access. Files metadata and compare are Python-owned; web download aliases remain Java-owned/unmigrated. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/files` | python | Public published version files metadata list with manager-only owner preview access for non-published versions. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/files` | python | Frontend alias for public published version files metadata list with manager-only owner preview access for non-published versions. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Public published tag files metadata list with authenticated context forwarding. Non-published tag targets remain rejected to match Java. |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Frontend alias for public published tag files metadata list with authenticated context forwarding. Non-published tag targets remain rejected to match Java. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/file` | python | Single file content bytes with manager-only owner-preview access for non-published versions. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/file` | python | Single file content bytes for published tag targets only. Non-published tag targets remain rejected to match Java. |
| GET | `/api/v1/skills/{namespace}/{slug}/download` | python | Latest portal download stream. Supports Java-compatible redirects upstream, headers, local bundle stream, fallback zip, and published counter increments. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/download` | python | Explicit version portal download stream. Java-compatible access allows public skill `PUBLISHED`, `UPLOADED`, and `PENDING_REVIEW`; counters increment only for `PUBLISHED`. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/download` | python | Tag-selected portal download stream with Java-compatible tag lookup and published counter increments. |
| GET | `/api/web/skills/{namespace}/{slug}/download` | java | Web download alias is not migrated; no Java evidence required moving it in this milestone. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/download` | java | Web download alias is not migrated; v1 portal download is Python-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/download` | java | Web download alias is not migrated; v1 tag download is Python-owned. |
| POST | `/api/v1/skills/{namespace}/publish` | python | Portal publish upload moved to Python and reuses the Python publish write service. |
| POST | `/api/web/skills/{namespace}/publish` | python | Frontend publish upload alias moved to Python and reuses the Python publish write service. |
| POST | `/api/cli/v1/skills/{namespace}/publish/validate` | python | CLI publish validate-only dry-run route. Multipart adapter over Python dry-run model; no DB/storage publish writes. |
| POST | `/api/cli/v1/skills/{namespace}/publish` | python | CLI publish write moved to Python after publish foundation, replacement, pending-review auto-withdraw, scanner handoff, and rollback live gates. |
| POST | `/api/v1/reviews` | python | Review submit write moved to Python. Moves `DRAFT`/`UPLOADED` versions to `PENDING_REVIEW`, creates a pending review task, and writes `REVIEW_SUBMIT` audit. Detail and file/download remain Java-owned. |
| POST | `/api/web/reviews` | python | Frontend review submit alias moved to Python with the same exact-POST ownership boundary as `/api/v1/reviews`. |
| GET | `/api/v1/reviews` | python | Review task global/namespace list moved to Python. Exact GET route only; detail and file/download remain Java-owned. |
| GET | `/api/web/reviews` | python | Frontend alias for review task global/namespace list. |
| GET | `/api/v1/reviews/pending` | python | Namespace pending review list moved to Python. |
| GET | `/api/web/reviews/pending` | python | Frontend alias for namespace pending review list. |
| GET | `/api/v1/reviews/my-submissions` | python | Current user's pending review submissions moved to Python. |
| GET | `/api/web/reviews/my-submissions` | python | Frontend alias for current user's pending review submissions. |
| GET | `/api/v1/reviews/{id}` | python | Review task detail moved to Python. Skill-detail, file, and download subroutes remain Java-owned. |
| GET | `/api/web/reviews/{id}` | python | Frontend alias for review task detail. |
| POST | `/api/v1/reviews/{id}/approve` | python | Review approval write moved to Python. Publishes the reviewed version, updates the skill latest/version visibility/metadata, and writes `REVIEW_APPROVE` audit. Other review routes remain Java-owned. |
| POST | `/api/web/reviews/{id}/approve` | python | Frontend review approval alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/approve`. |
| POST | `/api/v1/reviews/{id}/reject` | python | Review rejection write moved to Python. Rejects the review task, moves the version to `REJECTED`, and writes `REVIEW_REJECT` audit. |
| POST | `/api/web/reviews/{id}/reject` | python | Frontend review rejection alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/reject`. |
| POST | `/api/v1/reviews/{id}/withdraw` | python | Review withdraw write moved to Python. Submitter-only route deletes the pending review task, moves the version back to `UPLOADED`, updates skill `updated_by`, and writes `REVIEW_WITHDRAW` audit. |
| POST | `/api/web/reviews/{id}/withdraw` | python | Frontend review withdraw alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/withdraw`. |
| * | `/api/**` | java | Default owner for all routes not listed as Python-owned. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |
