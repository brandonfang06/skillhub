# Product Suite Namespace Admin Provisioning Design

**Date:** 2026-07-17
**Status:** Proposed for review
**Scope:** Organization-specific extension to the Python backend

## Problem

The organization maintains more than 60 SkillHub namespaces that correspond to
product suites. An organization API identifies each product suite and its
current owner by Windows account, such as `hcfange`.

SkillHub cannot add that owner before the first Keycloak login because:

- Keycloak login creates the `user_account` row and the random SkillHub
  `usr_<uuid>` identifier.
- The verified Keycloak `sub` is bound to that user through
  `identity_binding(provider_code, subject)`.
- `namespace_member.user_id` has a foreign key to `user_account.id`.

Creating a provisional SkillHub user from the Windows account would be unsafe.
The later OAuth login would not find that provisional row by Keycloak `sub`
and could create a second user, leaving the namespace role on the wrong
identity.

## Goals

- Record a product suite owner before that person has logged in to SkillHub.
- Add the person as namespace `ADMIN` after a trustworthy Keycloak login.
- Immediately add already-known SkillHub users during product suite sync.
- Treat product suite owner changes additively: add the new owner as `ADMIN`.
- Never replace the namespace `OWNER`.
- Do not automatically remove an `ADMIN` role that was already applied for a
  previous product suite owner.
- Keep login available when assignment reconciliation fails.
- Keep the extension isolated so upstream SkillHub releases remain practical
  to follow.

## Non-Goals

- Pre-creating fake or provisional `user_account` rows.
- Changing SkillHub user IDs or the Keycloak `provider + sub` identity model.
- Making product suite owners namespace `OWNER`.
- Automatically revoking previously applied namespace roles.
- Changing review, publish, search, notification, or visibility policies.
- Adding a frontend management page in the first implementation.
- Calling the product suite API from an OAuth request.

## Identity Contract

The product suite directory supplies a Windows account. Keycloak supplies the
same value as `preferred_username`; SkillHub stores it as the OAuth
`providerLogin`, updates `user_account.display_name`, and stores it in
`identity_binding.login_name`.

Assignment matching uses:

```text
identity provider registration id + normalized Windows account
```

Normalization is deterministic:

1. trim leading and trailing whitespace;
2. reject an empty value;
3. apply Unicode `casefold`;
4. enforce the existing 128-character login-name boundary.

Matching never uses fuzzy display-name search or email fallback. Once an
assignment is resolved, it stores the resulting SkillHub `user_id`; future
authorization continues to use the normal SkillHub UUID.

If more than one active Keycloak identity binding has the same normalized
login name, reconciliation fails closed with `CONFLICT`. It does not guess
which user should receive the role.

## Local Data Model

Organization-owned schema remains under
`server-python/app/db/local_migration/`; the upstream-followed
`server-python/app/db/migration/V*__*.sql` chain is unchanged.

### `local_product_suite_admin_assignment`

Each row represents one product-suite-owner observation:

| Column | Purpose |
| --- | --- |
| `id` | Local primary key |
| `source_system` | Stable source identifier, initially `product-suite-api` |
| `external_suite_id` | Stable product suite identifier from the source |
| `namespace_id` | Resolved SkillHub namespace |
| `identity_provider` | OAuth registration id, initially `keycloak` |
| `external_login` | Original Windows account for operator diagnostics |
| `normalized_external_login` | Exact normalized match key |
| `state` | `PENDING`, `APPLIED`, `RETAINED`, `SUPERSEDED`, `BLOCKED`, or `CONFLICT` |
| `source_current` | Whether the source still reports this person as current owner |
| `resolved_user_id` | SkillHub user after successful identity resolution |
| `first_seen_at` | First complete source snapshot containing this assignment |
| `last_seen_at` | Most recent complete source snapshot containing it |
| `applied_at` | Membership application time |
| `last_error` | Bounded operator-facing diagnostic |
| `created_at`, `updated_at` | Local record timestamps |

The schema enforces one current assignment per source product suite and an
idempotency key across source, suite, provider, and normalized login.

### `local_product_suite_assignment_event`

An append-only local event table records assignment lifecycle events:

- `OBSERVED`
- `APPLIED`
- `PROMOTED`
- `RETAINED`
- `SUPERSEDED`
- `BLOCKED`
- `CONFLICT`
- `RETRY_FAILED`

Events contain the assignment id, optional resolved user id, event time, sync
run identifier, and bounded detail JSON. This avoids changing the upstream
audit API while preserving an operator-visible history of automatic
permission changes.

## Source Synchronization

The product suite HTTP call runs outside request handling through a dedicated
Python command using the backend image. In Kubernetes, a CronJob can execute
that command with `concurrencyPolicy: Forbid`.

The integration has two boundaries:

- `ProductSuiteDirectoryClient` fetches and validates the complete external
  snapshot.
- `ProductSuiteAssignmentReconciler` receives normalized records containing
  `externalSuiteId`, `namespaceSlug`, and `ownerWindowsAccount`.

Keeping the reconciler independent from the organization HTTP response makes
source-specific parsing replaceable and easy to test. The concrete HTTP
adapter will be finalized against a sanitized API response and authentication
example before its implementation milestone.

Synchronization follows an all-before-write rule:

1. Fetch all pages from the product suite API.
2. Validate required fields, duplicate suite IDs, namespace mappings, and
   Windows accounts in memory.
3. If fetching or validation fails, write no assignment changes.
4. In one database transaction, resolve namespace slugs and upsert current
   observations.
5. Reconcile assignments against existing active Keycloak identity bindings.
6. Commit only after the full snapshot is processed.

The command is idempotent. Reprocessing the same snapshot does not create
duplicate memberships or events.

### Owner Change Rules

When the source changes from owner A to owner B:

- B becomes the current assignment and is applied as namespace `ADMIN` when
  resolvable.
- If A was already applied, A changes to `RETAINED`; the namespace membership
  remains and is not recreated if an administrator later removes it.
- If A was still pending, A changes to `SUPERSEDED` and must not be applied
  after a later login.
- The namespace's existing `OWNER` is unchanged.

When a previously known product suite is absent from a successfully validated
complete snapshot, its current assignment is deactivated. An applied
assignment becomes `RETAINED` and its namespace membership remains unchanged;
an unresolved assignment becomes `SUPERSEDED` and must not be applied after a
later login. No absence from the source snapshot automatically revokes an
already-applied namespace role.

## Membership Application Rules

The reconciler uses a dedicated system service rather than the interactive
namespace member route. It still preserves namespace lifecycle and role
invariants:

| Current namespace state | Result |
| --- | --- |
| Namespace missing | `BLOCKED` |
| Namespace frozen or archived | `BLOCKED`, retry after it becomes active |
| User missing | `PENDING` |
| User disabled or merged | `BLOCKED` |
| No membership | Insert `ADMIN` |
| Existing `MEMBER` | Promote to `ADMIN` |
| Existing `ADMIN` | No-op and mark `APPLIED` |
| Existing `OWNER` | No-op and mark `APPLIED`; never demote |

The product suite source cannot supply an arbitrary SkillHub role. The
integration hardcodes the desired role to `ADMIN`.

## OAuth Post-Bind Reconciliation

After Keycloak OAuth has successfully created or updated the normal
`user_account` and `identity_binding`, a narrow post-bind hook runs local
reconciliation for:

```text
provider code + provider login + resolved SkillHub user id
```

The hook:

- reads only the local assignment table;
- never performs an external HTTP call;
- applies current `PENDING` assignments;
- ignores `SUPERSEDED` and `RETAINED` assignments;
- executes in a separate transaction after identity binding commits;
- logs and records failures without rejecting the OAuth login.

The periodic synchronization command also retries unresolved and blocked
assignments. Therefore, a process interruption between OAuth binding and
membership application is eventually repaired.

## Operational Interface

The first implementation exposes a Python command, not a new public HTTP API:

```powershell
uv run python -m app.integrations.product_suite sync
```

Expected configuration categories are:

- feature enable flag;
- product suite API base URL;
- API authentication secret;
- Keycloak registration id;
- request timeout and page-size limits.

Exact environment variable names and the HTTP authentication/response parser
will be fixed in the implementation plan after reviewing a sanitized product
suite API example. Secrets belong in a Kubernetes Secret, not a ConfigMap.

The command emits structured counts for:

- suites fetched;
- namespaces resolved;
- assignments created or updated;
- existing users applied;
- pending users;
- conflicts and blocked assignments.

## Failure Behavior

- External API timeout, authorization failure, malformed pagination, or
  incomplete response: fail the sync command with no assignment changes.
- Unknown namespace: retain a blocked diagnostic; never create a namespace
  implicitly.
- Duplicate current owner rows for one suite: fail validation before writes.
- Duplicate active identity matches: mark `CONFLICT`; do not grant access.
- Membership write failure: roll back that reconciliation transaction and
  leave the assignment retryable.
- OAuth post-bind hook failure: log the error and allow login to finish.

No logs contain API tokens. Windows accounts may appear in restricted
operator logs and local assignment diagnostics because they are the explicit
business key for this integration.

## Upstream Isolation

The implementation should be concentrated in:

- one local migration file;
- `server-python/app/integrations/product_suite/`;
- focused backend tests;
- one narrow post-bind invocation in `server-python/app/auth/oauth.py`;
- an optional Kubernetes CronJob manifest and operator documentation.

It does not require changes to:

- upstream Flyway-numbered migrations;
- namespace member REST contracts;
- generated OpenAPI types;
- frontend pages;
- core authorization policy helpers.

When following a future upstream release, the recurring review is limited to:

1. verify the OAuth principal bind completion point still exists;
2. reattach the best-effort post-bind reconciler if that flow changes;
3. verify namespace membership and lifecycle invariants remain compatible;
4. preserve the local migration chain unless upstream adds an equivalent
   external-directory assignment feature.

## Verification Strategy

### Unit and Repository Tests

- Windows-account normalization and invalid boundaries.
- Complete-snapshot validation and no-write-on-invalid behavior.
- New assignment, unchanged snapshot, and owner-change state transitions.
- Old applied owner retained; old pending owner superseded.
- User lookup by Keycloak provider and normalized `login_name`.
- Duplicate identity conflict fails closed.
- Membership insert, `MEMBER` promotion, and `ADMIN`/`OWNER` no-op.
- Frozen, archived, disabled, merged, and missing-resource handling.
- Idempotent retries and event history.

### OAuth Regression Tests

- First login creates the normal identity before assignment reconciliation.
- Matching pending assignments are applied to the resolved UUID.
- Superseded assignments are ignored.
- Reconciliation exceptions do not fail OAuth login or session creation.
- Existing GitHub, GitLab, local login, and account merge behavior is
  unchanged.

### Database and Deployment Tests

- Existing V43 database applies the new local migration exactly once.
- Fresh database applies upstream and local migrations in order.
- PostgreSQL transaction tests cover owner-change and membership promotion.
- The sync command returns nonzero on source/validation failure.
- Kubernetes CronJob rendering uses the backend image and Secret-backed
  credentials.

### Final Gate

- Relevant focused tests.
- Full `server-python` pytest suite.
- Migration upgrade against PostgreSQL.
- Docker backend image build.
- Kubernetes manifest render.
- `git diff --check`.
- Review confirms no frontend, generated API, or upstream migration changes.

## Proposed Milestones

1. **Local assignment schema and state machine**
   - Add local migration, repository, normalization, and transition tests.
   - Verify migration idempotency and owner-change behavior.

2. **Existing-user reconciliation**
   - Resolve Keycloak login names and apply additive `ADMIN` membership.
   - Verify permission and namespace lifecycle boundaries with PostgreSQL
     transaction tests.

3. **OAuth post-bind reconciliation**
   - Add the narrow best-effort hook.
   - Verify login success, retry behavior, and auth regression coverage.

4. **Product suite sync adapter and command**
   - Freeze the external wire contract from a sanitized API example.
   - Implement complete-snapshot fetching, validation, idempotent sync, and
     structured results.

5. **Kubernetes and operator cutover**
   - Add the optional CronJob, Secret/ConfigMap contract, environment
     documentation, dry-run procedure, and rollback steps.
   - Run full backend, migration, image, and manifest verification.
