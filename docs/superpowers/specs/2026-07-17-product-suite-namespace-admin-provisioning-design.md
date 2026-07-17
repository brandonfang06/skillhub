# Product Suite Namespace Admin Daily Sync Design

**Date:** 2026-07-17
**Status:** Revised for review
**Scope:** Organization-specific synchronization command and Kubernetes CronJob

## Problem

The organization maintains more than 60 SkillHub namespaces that correspond to
product suites. An organization API identifies each product suite and its
current owner by Windows account, such as `hcfange`.

SkillHub cannot add an owner who has never logged in because
`namespace_member.user_id` must reference an existing `user_account`. The
Keycloak login creates that account and binds the verified Keycloak `sub` to a
random SkillHub `usr_<uuid>`.

The operational requirement does not need immediate role assignment after
login. A daily synchronization is sufficient. A person who logs in after the
daily job can receive the namespace role on the next run.

## Decision

Implement one idempotent Python synchronization command and run it once per day
from a Kubernetes CronJob.

The command:

1. fetches a complete product suite owner snapshot;
2. resolves each product suite to an existing SkillHub namespace;
3. finds an existing Keycloak identity by Windows account;
4. adds or promotes that SkillHub user to namespace `ADMIN`;
5. skips owners who have not logged in yet;
6. reports structured counts and errors;
7. repeats the same process on the next daily run.

There is no pending-assignment table and no OAuth integration.

## Goals

- Automatically add logged-in product suite owners as namespace `ADMIN`.
- Remove the current manual wait-then-add workflow.
- Retry owners who have not logged in simply by running the next daily sync.
- Add new product suite owners without changing the namespace `OWNER`.
- Keep previously granted administrators unless someone removes them manually.
- Keep the extension isolated from upstream SkillHub code.
- Make repeated and concurrent-safe runs produce the same membership state.

## Non-Goals

- Immediate role assignment in the OAuth callback.
- Pre-creating fake or provisional `user_account` rows.
- Persisting pending owners in SkillHub.
- Changing SkillHub UUID or Keycloak identity semantics.
- Making product suite owners namespace `OWNER`.
- Removing previous owners automatically.
- Adding a frontend page or public synchronization API.
- Changing review, publish, search, notification, or visibility behavior.

## Identity Matching

Keycloak supplies the Windows account as `preferred_username`. SkillHub stores
that value as OAuth `providerLogin`, updates `user_account.display_name`, and
stores it in `identity_binding.login_name`.

The sync command matches:

```text
identity_binding.provider_code = configured Keycloak registration id
normalized identity_binding.login_name = normalized Windows account
```

Normalization is deterministic:

1. trim leading and trailing whitespace;
2. reject empty values;
3. apply Unicode `casefold`;
4. enforce the existing 128-character login-name boundary.

The command never uses fuzzy display-name matching or email fallback. If more
than one active identity matches a normalized login, that record fails closed
as an identity conflict and receives no role.

## Product Suite To Namespace Mapping

Each normalized source record must contain:

```text
externalSuiteId
namespaceSlug
ownerWindowsAccount
```

The internal PIC module may obtain `namespaceSlug` directly from the
organization API or from an explicit configuration mapping keyed by stable
`externalSuiteId`. It must not guess a namespace from a display name.

## Internal Source Module Contract

The open-source repository does not implement the organization-specific PIC
HTTP client. It defines a stable Python boundary that the existing internal
`.py` module can implement:

```python
async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    ...
```

The shared types contain:

```python
@dataclass(frozen=True)
class ProductSuiteSourceConfig:
    api_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class ProductSuiteOwnerRecord:
    external_suite_id: str
    namespace_slug: str
    owner_windows_account: str
```

The internal module owns:

- PIC authentication;
- PIC pagination and response parsing;
- any organization-specific suite-to-namespace mapping;
- returning a complete list of normalized records.

The shared synchronization command owns:

- loading the configured source module;
- validating all returned records;
- resolving Keycloak identities;
- reconciling namespace membership;
- dry-run and structured result output.

The source module is trusted deployment code selected only by an operator. It
must be installed in the backend image or otherwise available on Python's
module path. The recommended organization deployment builds the internal
module into an organization-owned derivative backend image instead of mounting
executable Python through a ConfigMap.

## Daily Synchronization Flow

The product suite HTTP request occurs only inside the configured internal
source module invoked by the CronJob command:

```powershell
uv run python -m app.integrations.product_suite sync `
  --source-module company.pic_api `
  --api-url https://pic.example.internal/api
```

CLI values override environment values. The supported shared configuration is:

| CLI option | Environment variable | Purpose |
| --- | --- | --- |
| `--source-module` | `SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE` | Import path of the internal PIC module |
| `--api-url` | `SKILLHUB_PRODUCT_SUITE_API_URL` | Non-secret PIC API base URL |
| `--timeout-seconds` | `SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS` | Bounded source timeout |
| `--identity-provider` | `SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER` | OAuth registration id; defaults to `keycloak` |
| `--dry-run` | none | Report intended DB changes without writing |

PIC-specific credentials remain private to the internal source module and are
read from that module's own Secret-backed environment variables. The shared
command does not interpret or log those credentials.

The command performs:

1. Import the configured source module and validate its callable contract.
2. Ask the module for a complete normalized source snapshot.
3. Validate required fields, duplicate suite IDs, duplicate namespace
   mappings, and Windows account boundaries before database writes.
4. Open a database transaction.
5. Resolve every namespace slug without creating missing namespaces.
6. Resolve every Windows account through active Keycloak
   `identity_binding` and `user_account` rows.
7. Apply the additive `ADMIN` membership rules.
8. Commit after all valid records have been processed.
9. Print a structured summary and return a nonzero exit code when records need
   operator attention.

If the external API request or complete-snapshot validation fails, the command
writes no membership changes.

Owners who do not yet have a Keycloak identity are counted as
`waitingForLogin`. This is not a permanent error. The next daily run queries
the source again and applies the role if the user has logged in by then.
`waitingForLogin` alone does not make the command exit nonzero.

## Membership Rules

The command uses a dedicated organization integration service rather than the
interactive namespace member route. The only role it can grant is `ADMIN`.

| Condition | Result |
| --- | --- |
| Namespace missing | Report error; do not create it |
| Namespace frozen or archived | Skip and report blocked |
| User has never logged in | Count `waitingForLogin`; make no DB change |
| User disabled or merged | Skip and report blocked |
| User is not a member | Insert `namespace_member` as `ADMIN` |
| User is `MEMBER` | Promote to `ADMIN` |
| User is `ADMIN` | No-op |
| User is `OWNER` | No-op; never demote |

The operation is idempotent. Re-running the same snapshot does not create
duplicate members or unnecessary updates. Membership reconciliation uses the
existing `(namespace_id, user_id)` uniqueness boundary with an atomic upsert,
so an operator-triggered run overlapping the CronJob also converges safely.

## Owner Change And Manual Removal

When the product suite source changes from owner A to owner B:

- the next daily run adds B as namespace `ADMIN` if B has logged in;
- A remains namespace `ADMIN`;
- the namespace's existing `OWNER` remains unchanged.

If an administrator manually removes A after A is no longer the source owner,
later syncs do not add A again because A is absent from the current snapshot.

If an administrator manually removes B while B is still the current source
owner, the next daily sync adds B again. The current product suite owner is
authoritative for the additive `ADMIN` grant.

## Failure And Logging Behavior

- Source-module import, API, authentication, pagination, or incomplete
  snapshot failure: fail before database changes.
- Unknown namespace: report the external suite ID and namespace slug.
- Owner not logged in: report only as `waitingForLogin`.
- Duplicate active identity matches: report conflict and do not grant access.
- Membership write failure: roll back the synchronization transaction.
- Secrets are never written to logs.

The command emits a JSON-compatible summary containing:

- suites fetched;
- namespaces resolved;
- administrators added;
- members promoted;
- memberships already correct;
- owners waiting for first login;
- blocked records;
- identity conflicts;
- errors.

Kubernetes retains command output through the normal CronJob/Pod logging
system. The first version does not add a local history table.

## Kubernetes Operation

Add an optional CronJob manifest that reuses the Python backend image and the
same PostgreSQL connection configuration as the backend Deployment.

CronJob properties:

- daily schedule supplied in the manifest or overlay;
- `concurrencyPolicy: Forbid`;
- bounded retry count;
- `restartPolicy: Never`;
- product suite API credentials from a Secret;
- source module path, non-secret API URL, Keycloak provider id, and timeout
  from a ConfigMap.

The internal source module and its PIC credentials are organization-owned and
are not committed to the upstream-following repository.

The backend Deployment does not run a scheduler or background daemon. Running
the CronJob is the feature enablement boundary.

## Upstream Impact

This design has very low upstream impact:

- no database migration;
- no OAuth change;
- no namespace member REST contract change;
- no generated OpenAPI change;
- no frontend change;
- no authorization helper change.

New code is isolated under:

- `server-python/app/integrations/product_suite/`;
- focused backend tests;
- one optional Kubernetes CronJob manifest;
- environment and operator documentation.

The organization-specific PIC module remains outside the upstream-following
change set and depends only on the stable source contract.

The integration reads existing `identity_binding`, `user_account`, `namespace`,
and `namespace_member` tables and writes only the normal additive membership
state.

When following an upstream release, verify only that:

1. identity binding still exposes provider code and login name;
2. namespace lifecycle values remain compatible;
3. namespace membership roles remain `OWNER`, `ADMIN`, and `MEMBER`;
4. the backend image still contains the synchronization command.

## Verification Strategy

### Unit Tests

- Windows-account normalization.
- Normalized source-record validation.
- Source-module loading and contract validation.
- Complete-snapshot validation.
- Exact Keycloak identity matching.
- Duplicate identity conflict.
- Missing-login classification.
- Membership insert, promotion, and no-op behavior.
- Owner-change additive behavior.
- Idempotent repeated snapshots.

### Database Tests

- A logged-in owner becomes `ADMIN`.
- A never-logged-in owner produces no placeholder user or membership.
- A `MEMBER` becomes `ADMIN`.
- Existing `ADMIN` and `OWNER` rows remain unchanged.
- Frozen, archived, disabled, merged, and missing resources are skipped.
- A failed write rolls back the transaction.

### Deployment Tests

- Command exits zero for a complete successful run.
- Command exits nonzero for source or validation failure.
- Dry-run fixture confirms intended changes without writing.
- Kubernetes CronJob renders with Secret-backed credentials.
- Two attempted overlapping CronJobs are prevented by
  `concurrencyPolicy: Forbid`.

### Final Gate

- Focused integration tests.
- Full `server-python` pytest suite.
- Dry-run against a sanitized product suite snapshot.
- Live test with one existing user and one never-logged-in owner.
- Docker backend image build.
- Kubernetes manifest render.
- `git diff --check`.
- Review confirms no core schema, OAuth, frontend, or OpenAPI changes.

## Proposed Milestones

1. **Sync domain and database reconciliation**
   - Add the isolated command, normalized source model, identity resolver,
     membership reconciler, dry-run mode, and focused tests.
   - Verify existing, missing, promoted, blocked, and conflicting users.

2. **Kubernetes and internal PIC handoff**
   - Add the optional daily CronJob, source-module/API URL parameters,
     Secret/ConfigMap contract, environment documentation, dry-run procedure,
     rollback instructions, and an example test source module.
   - Verify the internal PIC module can return the shared record contract
     without adding PIC code to the upstream-following repository.
   - Run full backend, image, manifest, and live reconciliation verification.
