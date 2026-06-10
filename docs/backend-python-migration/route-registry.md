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
| GET | `/api/v1/auth/me` | python | Current local mock-user bridge for frontend auth context. OAuth callback/session/device-flow and bearer-token auth filters remain Java-owned. |
| GET | `/api/v1/whoami` | python | ClawHub current-principal read moved to Python. Returns plain `{ user: { handle, displayName, image } }` JSON, not `ApiResponse`. |
| GET | `/api/cli/v1/auth/whoami` | python | CLI current-principal read moved to Python. Returns Java-compatible `ApiResponse` envelope with `{ handle, displayName, email }`. |
| GET | `/api/v1/auth/providers` | python | Public OAuth provider catalog moved to Python. Preserves Java registration sorting, display-name fallback, OAuth authorization URL shape, and safe `returnTo` handling. |
| GET | `/api/v1/auth/methods` | python | Public auth method catalog moved to Python. Preserves Java local-password first entry, sorted OAuth methods, default-disabled direct/session-bootstrap methods, and safe `returnTo` handling. |
| POST | `/api/v1/auth/direct/login` | python | Direct login boundary moved to Python. Preserves Java default-disabled 403 and unsupported-provider ordering when enabled. Direct local delegates to migrated local login response, but final cookie/session persistence remains deferred. |
| POST | `/api/v1/auth/session/bootstrap` | python | Session bootstrap boundary moved to Python. Preserves Java default-disabled 403 and unsupported-provider ordering when enabled. Passive authenticator success/session persistence remains deferred because no production bootstrap provider exists in Java. |
| POST | `/api/v1/auth/local/register` | python | Local account register moved to Python. Preserves Java username/email normalization and validation, duplicate checks, password policy, active user/credential creation, global namespace membership, and local `AuthMeResponse` envelope. Spring Session creation remains deferred. |
| POST | `/api/v1/auth/local/login` | python | Local password login moved to Python. Preserves Java username normalization, BCrypt verification, account status rejection, failed-attempt lockout/reset, and local `AuthMeResponse` envelope. Spring Session creation remains deferred. |
| POST | `/api/v1/auth/local/change-password` | python | Local password change moved to Python for the hybrid mock-user bridge. Preserves Java local-credential requirement, current-password verification, password policy, credential hash update, and failed-attempt/lock reset. |
| POST | `/api/v1/auth/local/password-reset/request` | python | Anonymous local password reset request moved to Python. Preserves Java email normalization/validation, silent success for unknown or ineligible users, BCrypt reset code storage, old pending request consumption, and sender failure tolerance. |
| POST | `/api/v1/auth/local/password-reset/confirm` | python | Anonymous local password reset confirm moved to Python. Preserves Java six-digit code validation, password policy, invalid-code behavior, credential update/reset, and pending reset request consumption. |
| POST | `/api/v1/tokens` | python | API token create/rotate moved to Python. Requires current user, trims and validates names, rotates active same-name tokens, stores SHA-256 hashes only, and returns raw `sk_` token once. |
| GET | `/api/v1/tokens` | python | API token list moved to Python. Requires current user, returns active owner-scoped tokens ordered by `created_at DESC` with Java-compatible page envelope. |
| DELETE | `/api/v1/tokens/{id}` | python | API token revoke moved to Python. Requires current user, idempotently revokes only owner-scoped tokens, and returns `204` empty body. |
| PUT | `/api/v1/tokens/{id}/expiration` | python | API token expiration update moved to Python. Requires current user, updates only active owner-scoped tokens, accepts Java-compatible timestamp forms, and returns token summary. |
| GET | `/api/v1/skills` | python | ClawHub compatibility list. Static exact-path proxy also carries root publish `POST /api/v1/skills`; canonical skill mutations remain Java-owned. |
| POST | `/api/v1/skills` | python | ClawHub compatibility publish moved to Python. Accepts Java-compatible `payload` JSON plus repeated `files` parts and returns plain `{ ok, skillId, versionId }`. |
| POST | `/api/v1/publish` | python | Legacy ClawHub compatibility publish moved to Python. Accepts multipart zip `file` plus `namespace` and returns plain `{ ok, skillId, versionId }`. |
| GET | `/api/v1/skills/{canonicalSlug}` | python | ClawHub compatibility skill detail. GET-only method-aware proxy; publish, delete, and undelete remain Java-owned. |
| GET | `/api/web/skills` | python | Public portal skill search. `/api/v1/skills` remains Java-owned ClawHub compatibility. |
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | python | Public anonymous skill labels list. |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | python | Frontend alias for public anonymous skill labels list. |
| PUT | `/api/v1/skills/{namespace}/{slug}/labels/{labelSlug}` | python | Skill label attach moved to Python. Preserves owner/namespace-admin/super-admin permission rules, privileged-label restriction, max-label guard, idempotent existing attach, Java update envelope, and `SKILL_LABEL_ATTACH` audit. |
| PUT | `/api/web/skills/{namespace}/{slug}/labels/{labelSlug}` | python | Frontend alias for skill label attach. |
| DELETE | `/api/v1/skills/{namespace}/{slug}/labels/{labelSlug}` | python | Skill label detach moved to Python. Preserves owner/namespace-admin/super-admin permission rules, privileged-label restriction, missing-label error, Java delete envelope, and `SKILL_LABEL_DETACH` audit. |
| DELETE | `/api/web/skills/{namespace}/{slug}/labels/{labelSlug}` | python | Frontend alias for skill label detach. |
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
| GET | `/api/web/skills/{namespace}/{slug}/download` | python | Frontend alias for latest skill download. Shares the Python v1 download implementation and preserves Java stream headers and download counters. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/download` | python | Frontend alias for explicit version download. Shares the Python v1 download implementation and preserves Java stream headers and download counters. |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/download` | python | Frontend alias for tag download. Shares the Python v1 download implementation and preserves Java stream headers and download counters. |
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
| DELETE | `/api/v1/skills/{skillId}/star` | python | Authenticated idempotent unstar action moved to Python. Java v1 live policy still returns 403 for normal mock users through the broad hard-delete rule, so Python follows the Java controller/domain service contract instead. |
| DELETE | `/api/web/skills/{skillId}/star` | python | Frontend alias for authenticated idempotent unstar action. |
| GET | `/api/v1/skills/{skillId}/subscription` | python | Viewer subscription-state read moved to Python. Anonymous reads return Java-compatible `false`; authenticated reads validate skill existence and check `skill_subscription`. |
| GET | `/api/web/skills/{skillId}/subscription` | python | Frontend alias for viewer subscription-state read. |
| PUT | `/api/v1/skills/{skillId}/subscription` | python | Authenticated idempotent subscribe action moved to Python. Inserts `skill_subscription` when missing and increments `skill.subscription_count` once. |
| PUT | `/api/web/skills/{skillId}/subscription` | python | Frontend alias for authenticated idempotent subscribe action. |
| DELETE | `/api/v1/skills/{skillId}/subscription` | python | Authenticated idempotent unsubscribe action moved to Python. Java v1 live policy still returns 403 for normal mock users through the broad hard-delete rule, so Python follows the Java controller/domain service contract instead. |
| DELETE | `/api/web/skills/{skillId}/subscription` | python | Frontend alias for authenticated idempotent unsubscribe action. |
| GET | `/api/v1/skills/{skillId}/rating` | python | Authenticated viewer rating-state read moved to Python. Returns Java-compatible `{ score, rated }`. |
| GET | `/api/web/skills/{skillId}/rating` | python | Frontend alias for authenticated viewer rating-state read. |
| PUT | `/api/v1/skills/{skillId}/rating` | python | Authenticated rating create/update moved to Python. Validates score 1..5, upserts `skill_rating`, and refreshes `skill.rating_avg` / `skill.rating_count`. |
| PUT | `/api/web/skills/{skillId}/rating` | python | Frontend alias for authenticated rating create/update. |
| GET | `/api/v1/me/stars` | python | Current user's starred skill list moved to Python. Requires auth, defaults to `page=0&size=12`, preserves Java page envelope and summary shape. |
| GET | `/api/web/me/stars` | python | Frontend alias for current user's starred skill list. |
| GET | `/api/v1/me/subscriptions` | python | Current user's subscribed skill list moved to Python. Requires auth, defaults to `page=0&size=12`, preserves Java page envelope and summary shape. |
| GET | `/api/web/me/subscriptions` | python | Frontend alias for current user's subscribed skill list. |
| GET | `/api/v1/me/skills` | python | Current user's owned skill list moved to Python. Requires auth, preserves Java defaults `page=0&size=10`, filter/q/namespace behavior, owner lifecycle projection, and hidden/archived filter semantics. |
| GET | `/api/web/me/skills` | python | Frontend alias for current user's owned skill list. |
| GET | `/api/v1/namespaces` | python | Current user's active namespace list moved to Python. Requires auth, derives namespace scope from `namespace_member`, sorts by slug, and preserves Java `PageResponse`. |
| GET | `/api/web/namespaces` | python | Frontend alias for current user's active namespace list. |
| GET | `/api/v1/me/namespaces` | python | Current user's namespace membership list moved to Python. Includes Java-compatible lifecycle capability flags and dependency-sensitive `canDelete`. |
| GET | `/api/web/me/namespaces` | python | Frontend alias for current user's namespace membership list. |
| GET | `/api/v1/namespaces/{slug}` | python | Namespace detail read moved to Python. Requires namespace membership; archived namespaces remain visible only to members. |
| GET | `/api/web/namespaces/{slug}` | python | Frontend alias for namespace detail read. Namespace management mutations are Python-owned below. |
| POST | `/api/v1/namespaces` | python | Namespace create moved to Python. Requires `SKILL_ADMIN` or `SUPER_ADMIN`, validates slug, creates a TEAM/ACTIVE namespace, and grants creator OWNER. |
| POST | `/api/web/namespaces` | python | Frontend alias for namespace create. |
| PUT | `/api/v1/namespaces/{slug}` | python | Namespace profile update moved to Python. Requires namespace OWNER/ADMIN and active team namespace. |
| PUT | `/api/web/namespaces/{slug}` | python | Frontend alias for namespace profile update. |
| DELETE | `/api/v1/namespaces/{slug}` | python | Namespace delete moved to Python. Requires namespace OWNER, rejects immutable/dependent namespaces, removes members, and deletes namespace row. |
| DELETE | `/api/web/namespaces/{slug}` | python | Frontend alias for namespace delete. |
| POST | `/api/v1/namespaces/{slug}/freeze` | python | Namespace freeze moved to Python. OWNER/ADMIN can transition ACTIVE to FROZEN and write `FREEZE_NAMESPACE` audit. |
| POST | `/api/web/namespaces/{slug}/freeze` | python | Frontend alias for namespace freeze. |
| POST | `/api/v1/namespaces/{slug}/unfreeze` | python | Namespace unfreeze moved to Python. OWNER/ADMIN can transition FROZEN to ACTIVE and write `UNFREEZE_NAMESPACE` audit. |
| POST | `/api/web/namespaces/{slug}/unfreeze` | python | Frontend alias for namespace unfreeze. |
| POST | `/api/v1/namespaces/{slug}/archive` | python | Namespace archive moved to Python. OWNER can transition non-archived team namespace to ARCHIVED and write `ARCHIVE_NAMESPACE` audit. |
| POST | `/api/web/namespaces/{slug}/archive` | python | Frontend alias for namespace archive. |
| POST | `/api/v1/namespaces/{slug}/restore` | python | Namespace restore moved to Python. OWNER can transition ARCHIVED to ACTIVE and write `RESTORE_NAMESPACE` audit. |
| POST | `/api/web/namespaces/{slug}/restore` | python | Frontend alias for namespace restore. |
| GET | `/api/v1/namespaces/{slug}/members` | python | Namespace member list moved to Python. Requires namespace membership and preserves Java `PageResponse<MemberResponse>` shape. |
| GET | `/api/web/namespaces/{slug}/members` | python | Frontend alias for namespace member list. |
| GET | `/api/v1/namespaces/{slug}/member-candidates` | python | Namespace member candidate search moved to Python. Requires namespace `OWNER` or `ADMIN`, rejects immutable/read-only namespaces, trims search, enforces Java size defaults/cap, filters ACTIVE users, and excludes existing members. |
| GET | `/api/web/namespaces/{slug}/member-candidates` | python | Frontend alias for namespace member candidate search. |
| POST | `/api/v1/namespaces/{slug}/members` | python | Namespace member add moved to Python. Preserves Java active-team/admin-or-owner checks, duplicate detection, and owner-direct assignment rejection. |
| POST | `/api/web/namespaces/{slug}/members` | python | Frontend alias for namespace member add. |
| DELETE | `/api/v1/namespaces/{slug}/members/{userId}` | python | Namespace member remove moved to Python. Preserves Java missing-member and owner-remove rejection. |
| DELETE | `/api/web/namespaces/{slug}/members/{userId}` | python | Frontend alias for namespace member remove. |
| PUT | `/api/v1/namespaces/{slug}/members/{userId}/role` | python | Namespace member role update moved to Python. Preserves Java owner-direct role update rejection. |
| PUT | `/api/web/namespaces/{slug}/members/{userId}/role` | python | Frontend alias for namespace member role update. |
| POST | `/api/v1/namespaces/{slug}/members/batch` | python | Namespace member batch add moved to Python. Preserves Java partial-success behavior and batch error mapping. |
| POST | `/api/web/namespaces/{slug}/members/batch` | python | Frontend alias for namespace member batch add. |
| POST | `/api/v1/namespaces/{slug}/transfer-ownership` | python | Namespace ownership transfer moved to Python. Requires current owner, swaps old owner to `ADMIN` and new owner to `OWNER`, and keeps namespace lifecycle/profile APIs Java-owned. |
| POST | `/api/web/namespaces/{slug}/transfer-ownership` | python | Frontend alias for namespace ownership transfer. |
| GET | `/api/v1/notifications` | python | Current user's notification list moved to Python. Requires auth, preserves Java `PageResponse` envelope, category validation, target resolution, and created-at descending order. |
| GET | `/api/web/notifications` | python | Frontend alias for current user's notification list. |
| GET | `/api/v1/notifications/unread-count` | python | Current user's unread notification count moved to Python. Returns Java-compatible `{ count }`. |
| GET | `/api/web/notifications/unread-count` | python | Frontend alias for unread notification count. |
| PUT | `/api/v1/notifications/{id}/read` | python | Mark-one-read moved to Python. Missing ids return `error.notification.notFound`; foreign ids return `error.notification.noPermission`; success returns Java-compatible update envelope with `data = null`. |
| PUT | `/api/web/notifications/{id}/read` | python | Frontend alias for mark-one-read. |
| PUT | `/api/v1/notifications/read-all` | python | Mark-all-read moved to Python. Returns Java-compatible `{ updated }`. |
| PUT | `/api/web/notifications/read-all` | python | Frontend alias for mark-all-read. |
| DELETE | `/api/v1/notifications/{id}` | python | Delete-read notification moved to Python. Deletes only current-user `READ` notifications; otherwise returns `error.notification.readNotFound`. |
| DELETE | `/api/web/notifications/{id}` | python | Frontend alias for delete-read notification. |
| GET | `/api/v1/notifications/sse` | java | SSE stream remains Java-owned. |
| GET | `/api/web/notifications/sse` | java | Frontend SSE stream remains Java-owned. |
| GET | `/api/v1/notification-preferences` | python | Current user's notification preferences moved to Python. Returns all Java notification categories in enum order with `IN_APP` channel and default `enabled = true` for missing rows. |
| GET | `/api/web/notification-preferences` | python | Frontend alias for notification preference read. |
| PUT | `/api/v1/notification-preferences` | python | Notification preference update moved to Python. Validates Java-compatible category/channel/duplicate rules, upserts `notification_preference`, and returns the full preference list. |
| PUT | `/api/web/notification-preferences` | python | Frontend alias for notification preference update. |
| GET | `/api/v1/admin/labels` | python | Admin label definition list moved to Python. Requires `SUPER_ADMIN`, preserves Java sort order and response shape. |
| POST | `/api/v1/admin/labels` | python | Admin label definition create moved to Python. Requires `SUPER_ADMIN`, normalizes slug/translations, writes label rows, and records `LABEL_CREATE` audit. |
| PUT | `/api/v1/admin/labels/{slug}` | python | Admin label definition update moved to Python. Requires `SUPER_ADMIN`, replaces translations, updates type/visibility/sort order, and records `LABEL_UPDATE` audit. |
| DELETE | `/api/v1/admin/labels/{slug}` | python | Admin label definition delete moved to Python. Requires `SUPER_ADMIN`, deletes the definition through DB cascade and records `LABEL_DELETE` audit. |
| PUT | `/api/v1/admin/labels/sort-order` | python | Admin label definition sort update moved to Python. Requires `SUPER_ADMIN`, updates per-label sort order and records `LABEL_SORT_ORDER_UPDATE` audit. |
| GET | `/api/v1/admin/users` | python | Admin user list moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, preserves Java search/status/page behavior, created-at descending order, role fallback to `USER`, and page envelope. |
| PUT | `/api/v1/admin/users/{userId}/role` | python | Admin user role update moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, deletes previous platform bindings, preserves `USER` as no binding, and keeps `SUPER_ADMIN` assignment restricted to super admins. |
| PUT | `/api/v1/admin/users/{userId}/status` | python | Admin user status update moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, allows only Java-manageable `ACTIVE`/`DISABLED` transitions, and returns Java-compatible mutation envelope. |
| POST | `/api/v1/admin/users/{userId}/approve` | python | Admin user approve alias moved to Python. Sets status to `ACTIVE` with the same mutation contract as Java. |
| POST | `/api/v1/admin/users/{userId}/disable` | python | Admin user disable alias moved to Python. Sets status to `DISABLED` with the same mutation contract as Java. |
| POST | `/api/v1/admin/users/{userId}/enable` | python | Admin user enable alias moved to Python. Sets status to `ACTIVE` with the same mutation contract as Java. |
| POST | `/api/v1/admin/users/{userId}/password-reset` | python | Admin-triggered password reset moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, preserves Java eligibility checks, consumes old pending requests, writes BCrypt-compatible admin reset rows, and exposes a sender hook for later SMTP parity. |
| GET | `/api/v1/admin/audit-logs` | python | Admin audit log read moved to Python. Requires `AUDITOR` or `SUPER_ADMIN`, preserves Java filters, details fallback, UTC timestamps, and page envelope. |
| GET | `/api/v1/admin/skill-reports` | python | Admin skill report list moved to Python. Requires `SKILL_ADMIN` or `SUPER_ADMIN`, preserves Java status parsing, skill/namespace summary projection, and page envelope. |
| POST | `/api/v1/admin/skill-reports/{reportId}/resolve` | python | Admin skill report resolve moved to Python. Requires `SKILL_ADMIN` or `SUPER_ADMIN`, restricts `RESOLVE_AND_HIDE` to `SUPER_ADMIN`, preserves report state mutation, optional skill hide/archive side effects, audit logs, and legacy report notification. |
| POST | `/api/v1/admin/skill-reports/{reportId}/dismiss` | python | Admin skill report dismiss moved to Python. Requires `SKILL_ADMIN` or `SUPER_ADMIN`, preserves pending-only transition, trimmed handle comment, audit log, and legacy report notification. |
| GET | `/api/v1/admin/profile-reviews` | python | Admin profile review list moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, preserves Java status parsing, sort behavior, JSON snapshot fallback, reviewer projection, and page envelope. |
| POST | `/api/v1/admin/profile-reviews/{id}/approve` | python | Admin profile review approve moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, preserves pending-only transition, display-name application, and audit log. |
| POST | `/api/v1/admin/profile-reviews/{id}/reject` | python | Admin profile review reject moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, preserves pending-only transition, review comment, and audit log detail JSON. |
| POST | `/api/v1/skills/{namespace}/{slug}/reports` | python | Skill report submit moved to Python. Requires auth, resolves Java published-preference skill target, rejects blank/self/duplicate/unavailable reports, writes `skill_report`, `REPORT_SKILL` audit, and `REPORT_SUBMITTED` notifications. |
| POST | `/api/web/skills/{namespace}/{slug}/reports` | python | Frontend alias for skill report submit with the same ownership boundary as `/api/v1/skills/{namespace}/{slug}/reports`. |
| GET | `/api/v1/governance/summary` | python | Governance summary read moved to Python. Preserves Java platform/namespace-scoped pending counts and legacy `user_notification` unread count. |
| GET | `/api/web/governance/summary` | python | Frontend alias for governance summary read. |
| GET | `/api/v1/governance/inbox` | python | Governance inbox read moved to Python. Preserves Java review/promotion/report merge behavior, namespace/platform visibility, type filtering, and page envelope. |
| GET | `/api/web/governance/inbox` | python | Frontend alias for governance inbox read. |
| GET | `/api/v1/governance/activity` | python | Governance activity read moved to Python. Platform governance roles and `AUDITOR` can read audit-derived activity; other users receive Java-compatible empty pages. |
| GET | `/api/web/governance/activity` | python | Frontend alias for governance activity read. |
| GET | `/api/v1/governance/notifications` | python | Legacy governance notification list moved to Python. Reads `user_notification` rather than the newer `notification` table to match Java. |
| GET | `/api/web/governance/notifications` | python | Frontend alias for legacy governance notification list. |
| POST | `/api/v1/governance/notifications/{id}/read` | python | Legacy governance notification mark-read moved to Python. Reads and updates `user_notification`, preserves Java owner guard, `error.notification.notFound`, `error.notification.noPermission`, and `更新成功` response. |
| POST | `/api/web/governance/notifications/{id}/read` | python | Frontend alias for legacy governance notification mark-read. |
| * | `/api/**` | java | Default owner for all routes not listed as Python-owned. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |
