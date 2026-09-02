# OSS Namespace Platform Admin Membership

**Date:** 2026-09-02

## Goal

When the source-import API creates a new repository namespace whose canonical
slug starts with `oss-`, the platform admin who created the importer service
principal must also be the namespace `ADMIN`.

The configured fallback user remains the single namespace `OWNER`. The service
principal remains the machine audit actor and never becomes a namespace member.

## Scope

- Apply the rule only inside the existing source-import namespace creation
  transaction.
- Resolve the exact user through `service_principal.created_by_user_id`, require
  `user_account.status=ACTIVE`, and require a current `SUPER_ADMIN` binding.
- Insert one `namespace_member(role=ADMIN)` row for that user.
- Require the fallback owner and platform admin to be different users so every
  newly created OSS namespace has exactly two management-role members: one
  `OWNER` and one `ADMIN`.
- Keep repeated ensure calls idempotent. An already-bound namespace is returned
  unchanged and is not backfilled by this change. Concurrent ensures for the
  same derived slug use a transaction-scoped PostgreSQL advisory lock. An
  overlapping request fails fast with a retryable conflict instead of waiting
  indefinitely; retry after the first commit resolves to `EXISTING`.
- Keep the HTTP request and response contracts, importer configuration, skill
  ownership, review submission, visibility, and scanner behavior unchanged.

The existing source-submission flow may later add a resolved pipeline initiator
as namespace `MEMBER`. That attribution membership is not a management role and
is intentionally unchanged.

Backfilling existing `oss-` namespaces and synchronizing memberships when a
platform role changes are separate governance operations and are not part of
this change.

## Transaction And Audit

Namespace, owner membership, platform-admin memberships, source binding, and
`CREATE_OSS_SOURCE_NAMESPACE` audit evidence must commit or roll back together.
The audit detail records the resolved platform-admin user ID.

No new environment variable, schema migration, route, or external side effect
is required.

## Security Review

- **Confidentiality:** no new protected data crosses a trust boundary. User IDs
  already used by RBAC and namespace membership are stored in the existing
  membership and audit tables.
- **Integrity:** only the service principal's active `SUPER_ADMIN` creator
  qualifies, and that user must differ from the configured owner. All writes
  share the source-import database transaction and authenticated
  service-principal audit actor.
- **Availability:** a database failure during membership or audit persistence
  rolls back the namespace and source binding. Advisory lock contention fails
  fast instead of waiting without a bound. Retry therefore starts from a clean
  state; no external notification or storage operation is introduced.

Abuse and failure cases to verify include an inactive creator, a creator without
the exact role, unrelated platform admins, a creator who is also the configured
owner, repeated ensure, and forced failure after all creation writes.

## Verification

1. Unit tests prove the service preserves existing namespace behavior and
   forwards no client-controlled role or member list.
2. A real PostgreSQL test proves the exact resulting membership rows, audit
   detail, idempotent retry, inactive-user exclusion, and transaction rollback.
3. Run the focused source-import tests, full backend suite, formatter/linter
   checks used by the backend, the containerized OSS source-import smoke,
   `git diff --check`, and review the complete diff from `origin/dev`.
