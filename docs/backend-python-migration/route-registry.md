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
| GET | `/api/v1/reviews/{id}` | python | Review task detail moved to Python. |
| GET | `/api/web/reviews/{id}` | python | Frontend alias for review task detail. |
| GET | `/api/v1/reviews/{id}/skill-detail` | python | Review-bound skill detail moved to Python. Uses the review task's active version snapshot, Java lifecycle ordering, storage-backed documentation content, and review download URL. |
| GET | `/api/web/reviews/{id}/skill-detail` | python | Frontend alias for review-bound skill detail. |
| GET | `/api/v1/reviews/{id}/file` | python | Review-bound single-file content moved to Python. Returns raw `application/octet-stream` bytes from the review task's active version and preserves Java path validation. |
| GET | `/api/web/reviews/{id}/file` | python | Frontend alias for review-bound single-file content. |
| GET | `/api/v1/reviews/{id}/download` | python | Review-bound package download moved to Python. Streams the review task's active version bundle/fallback zip without public download counter increments. |
| GET | `/api/web/reviews/{id}/download` | python | Frontend alias for review-bound package download. |
| GET | `/api/v1/promotions` | python | Promotion request list moved to Python. Requires platform review role (`SKILL_ADMIN` or `SUPER_ADMIN`) and keeps write routes Java-owned. |
| GET | `/api/web/promotions` | python | Frontend alias for promotion request list. |
| GET | `/api/v1/promotions/pending` | python | Pending promotion list moved to Python. Requires platform review role. |
| GET | `/api/web/promotions/pending` | python | Frontend alias for pending promotion list. |
| GET | `/api/v1/promotions/{id}` | python | Promotion detail moved to Python. Submitter or platform review role can read. |
| GET | `/api/web/promotions/{id}` | python | Frontend alias for promotion detail. |
| POST | `/api/v1/promotions` | python | Promotion submit moved to Python. Creates `promotion_request`, enforces source ownership/platform/namespace role permission, duplicate checks, and writes `PROMOTION_SUBMIT` audit. |
| POST | `/api/web/promotions` | python | Frontend promotion submit alias moved to Python with the same ownership boundary as `/api/v1/promotions`. |
| POST | `/api/v1/promotions/{id}/approve` | python | Promotion approval moved to Python. Platform reviewer only, self-review forbidden, materializes public target skill/version/file records in the target global namespace, writes `PROMOTION_APPROVE` audit and synchronous governance notification. |
| POST | `/api/web/promotions/{id}/approve` | python | Frontend promotion approval alias moved to Python with the same ownership boundary as `/api/v1/promotions/{id}/approve`. |
| POST | `/api/v1/promotions/{id}/reject` | python | Promotion reject moved to Python. Platform reviewer only, self-review forbidden, updates request to `REJECTED`, writes `PROMOTION_REJECT` audit and synchronous governance notification. |
| POST | `/api/web/promotions/{id}/reject` | python | Frontend promotion reject alias moved to Python with the same ownership boundary as `/api/v1/promotions/{id}/reject`. |
| POST | `/api/v1/reviews/{id}/approve` | python | Review approval write moved to Python. Publishes the reviewed version, updates the skill latest/version visibility/metadata, and writes `REVIEW_APPROVE` audit. Other review routes remain Java-owned. |
| POST | `/api/web/reviews/{id}/approve` | python | Frontend review approval alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/approve`. |
| POST | `/api/v1/reviews/{id}/reject` | python | Review rejection write moved to Python. Rejects the review task, moves the version to `REJECTED`, and writes `REVIEW_REJECT` audit. |
| POST | `/api/web/reviews/{id}/reject` | python | Frontend review rejection alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/reject`. |
| POST | `/api/v1/reviews/{id}/withdraw` | python | Review withdraw write moved to Python. Submitter-only route deletes the pending review task, moves the version back to `UPLOADED`, updates skill `updated_by`, and writes `REVIEW_WITHDRAW` audit. |
| POST | `/api/web/reviews/{id}/withdraw` | python | Frontend review withdraw alias moved to Python with the same ownership boundary as `/api/v1/reviews/{id}/withdraw`. |
| POST | `/api/v1/skills/{namespace}/{slug}/archive` | python | Portal skill archive moved to Python. Owner or namespace `OWNER`/`ADMIN` can set `skill.status = ARCHIVED`, update `updated_by`, and write `ARCHIVE_SKILL` audit. |
| POST | `/api/web/skills/{namespace}/{slug}/archive` | python | Frontend skill archive alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/archive`. |
| POST | `/api/v1/skills/{namespace}/{slug}/unarchive` | python | Portal skill unarchive moved to Python. Owner or namespace `OWNER`/`ADMIN` can set `skill.status = ACTIVE`, update `updated_by`, and write `UNARCHIVE_SKILL` audit. |
| POST | `/api/web/skills/{namespace}/{slug}/unarchive` | python | Frontend skill unarchive alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/unarchive`. |
| DELETE | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | python | Portal version delete moved to Python. Deletes only `DRAFT`/`REJECTED`/`SCAN_FAILED`/`UPLOADED`, clears files, soft-deletes security audit rows, recalculates latest published pointer, writes `DELETE_SKILL_VERSION` audit, and deletes local storage with compensation on failure. |
| DELETE | `/api/web/skills/{namespace}/{slug}/versions/{version}` | python | Frontend version delete alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/versions/{version}`. |
| POST | `/api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | python | Portal version withdraw-review moved to Python. Only the pending review task submitter can withdraw; the route deletes the pending task, moves the version back to `UPLOADED`, updates `skill.updated_by`, and writes `REVIEW_WITHDRAW` audit. |
| POST | `/api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review` | python | Frontend version withdraw-review alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review`. |
| POST | `/api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease` | python | Portal version rerelease moved to Python. Owner or namespace `OWNER`/`ADMIN` can rebuild a new target version from a `PUBLISHED` source version, rewrite `SKILL.md` version, reuse publish orchestration, and write `RERELEASE_SKILL_VERSION` audit. |
| POST | `/api/web/skills/{namespace}/{slug}/versions/{version}/rerelease` | python | Frontend version rerelease alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease`. |
| POST | `/api/v1/skills/{namespace}/{slug}/confirm-publish` | python | Portal confirm-publish moved to Python. Owner or namespace `OWNER`/`ADMIN` can publish a PRIVATE `UPLOADED`/`DRAFT` version directly, set `published_at`, update `skill.latest_version_id`/`updated_by`, and write `CONFIRM_PUBLISH` audit. |
| POST | `/api/web/skills/{namespace}/{slug}/confirm-publish` | python | Frontend confirm-publish alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/confirm-publish`. |
| POST | `/api/v1/skills/{namespace}/{slug}/submit-review` | python | Portal submit-review moved to Python. Owner or namespace `OWNER`/`ADMIN` can submit an `UPLOADED`/`DRAFT` version for `PUBLIC` or `NAMESPACE_ONLY` review, persist `requested_visibility`, create a pending review task, and write `SUBMIT_REVIEW` lifecycle audit. |
| POST | `/api/web/skills/{namespace}/{slug}/submit-review` | python | Frontend submit-review alias moved to Python with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/submit-review`. |
| POST | `/api/v1/admin/skills/{skillId}/hide` | python | Platform-admin skill hide moved to Python. `SUPER_ADMIN` only; sets the hidden overlay, preserves `skill.status`, updates audit fields, and writes `HIDE_SKILL` audit with optional reason detail. |
| POST | `/api/v1/admin/skills/{skillId}/unhide` | python | Platform-admin skill unhide moved to Python. `SUPER_ADMIN` only; clears the hidden overlay, preserves `skill.status`, updates audit fields, and writes `UNHIDE_SKILL` audit. |
| POST | `/api/v1/admin/skills/versions/{versionId}/yank` | python | Admin version yank moved to Python. `SKILL_ADMIN` or `SUPER_ADMIN` can yank only `PUBLISHED` versions, recalculate the skill latest pointer when needed, disable downloads, and write `YANK_SKILL_VERSION` audit. |
| GET | `/api/v1/skills/{skillId}/star` | python | Authenticated viewer star-state read moved to Python. Anonymous requests are rejected to match live Java security. |
| GET | `/api/web/skills/{skillId}/star` | python | Frontend alias for authenticated viewer star-state read. |
| PUT | `/api/v1/skills/{skillId}/star` | python | Authenticated idempotent star action moved to Python. Inserts `skill_star` when missing and refreshes `skill.star_count`. |
| PUT | `/api/web/skills/{skillId}/star` | python | Frontend alias for authenticated idempotent star action. |
| DELETE | `/api/v1/skills/{skillId}/star` | java | Unstar remains Java-owned/deferred. Live Java v1 security currently returns 403 for a normal local mock user through the broader `DELETE /api/v1/skills/*/*` policy. |
| DELETE | `/api/web/skills/{skillId}/star` | java | Web unstar remains Java-owned through the Vite fallback and should move later with the broader social/security cleanup. |
| GET | `/api/v1/skills/{skillId}/subscription` | python | Viewer subscription-state read moved to Python. Anonymous reads return Java-compatible `false`; authenticated reads validate skill existence and check `skill_subscription`. |
| GET | `/api/web/skills/{skillId}/subscription` | python | Frontend alias for viewer subscription-state read. |
| PUT | `/api/v1/skills/{skillId}/subscription` | python | Authenticated idempotent subscribe action moved to Python. Inserts `skill_subscription` when missing and increments `skill.subscription_count` once. |
| PUT | `/api/web/skills/{skillId}/subscription` | python | Frontend alias for authenticated idempotent subscribe action. |
| DELETE | `/api/v1/skills/{skillId}/subscription` | java | Unsubscribe remains Java-owned/deferred. Live Java v1 security currently returns 403 for a normal local mock user through the broader `DELETE /api/v1/skills/*/*` policy. |
| DELETE | `/api/web/skills/{skillId}/subscription` | java | Web unsubscribe remains Java-owned through the Vite fallback and should move later with the broader social/security cleanup. |
| * | `/api/**` | java | Default owner for all routes not listed as Python-owned. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |
