# OSS GitHub Source Import GitLab Design

**Status:** Approved
**Date:** 2026-08-18

## Problem

Platform users need a repeatable GitLab pipeline job that imports all agent
skills from a checked-out public GitHub repository into SkillHub. The job must
create or reuse a repository-specific namespace, attribute imported skills to
the pipeline initiator when possible, preserve an auditable link to the exact
OSS source, and submit every imported version through the existing scanner and
namespace-owner review lifecycle.

The source repository is already present in the GitLab Runner checkout. The
feature does not clone GitHub repositories and does not make the SkillHub
backend fetch arbitrary external URLs.

## Outcome

Provide:

- a Python OSS source importer with a console command;
- a dedicated importer container image suitable for GitLab Runner;
- a reusable GitLab CI template and Chinese operating procedure;
- narrow bearer-authenticated FastAPI endpoints for namespace provisioning,
  validation, and one-skill-at-a-time submission;
- Python-owned PostgreSQL provenance tables and migrations;
- source provenance in review and skill-version read models;
- root and `/skillhub` deployment compatibility; and
- end-to-end verification against PostgreSQL, Redis, object storage, scanner,
  backend, and the public web/proxy entrypoint.

Example input:

```text
https://github.com/mattpocock/skills
```

Example namespace:

```text
slug:         oss-mattpocock-skills
display name: OSS-mattpocock-skills
```

## Selected Architecture

Use a Python importer plus narrow SkillHub source-import APIs.

The importer owns repository-local work:

- validate and canonicalize the declared GitHub repository URL;
- read the GitLab checkout and commit context;
- discover exact `SKILL.md` files;
- form independent skill roots;
- create deterministic packages;
- request a deterministic version override when the source omits one, without
  modifying source files in the package;
- validate every package before submitting any package;
- submit packages one at a time; and
- produce human-readable logs and a machine-readable JSON report.

The SkillHub backend owns platform state and policy:

- authenticate and authorize the importer service account;
- resolve OAuth identities using `provider_code + login_name`;
- create or verify the repository namespace;
- preserve namespace governance;
- select the effective skill owner;
- enforce package, lifecycle, and replacement rules;
- store source provenance and idempotency evidence;
- enqueue the existing scanner/review workflow; and
- write audit evidence for the service actor and effective owner.

The backend does not clone repositories, enumerate filesystem trees, or accept
an entire multi-skill repository as one bulk upload.

### Considered alternatives

1. **Python importer plus narrow APIs (selected).** Keeps repository concerns
   in the runner and durable platform policy in SkillHub.
2. **Compose existing namespace and publish APIs.** Rejected because current
   namespace routes do not support the required bearer automation, effective
   owner attribution, source provenance, or idempotent repository binding.
3. **One bulk-import backend endpoint.** Rejected because it creates a large
   request, complex cross-package rollback, and an unnecessarily deep coupling
   between backend and repository orchestration.

## Domain Terms

- **Declared source repository:** the canonical `https://github.com/owner/repo`
  URL supplied to the pipeline. It is an identity assertion, not an instruction
  for the backend to fetch the repository.
- **Repository revision:** the exact checkout commit supplied by
  `CI_COMMIT_SHA` and verified against `git rev-parse HEAD`.
- **Source ref:** an optional Git tag or branch label associated with the
  checkout. It is descriptive and does not replace the immutable commit SHA.
- **Skill source path:** the repository-relative parent directory of one exact
  `SKILL.md`. Within a repository namespace, this path is the stable source
  identity for the imported skill container.
- **Source content fingerprint:** a backend-computed SHA-256 fingerprint over
  sorted package paths and file-content digests. It determines whether source
  content is unchanged.
- **Importer actor:** the SkillHub service account identified by the bearer
  token. It authorizes and audits the pipeline operation.
- **Pipeline initiator:** the person whose Keycloak `preferred_username` is
  passed by the GitLab pipeline.
- **Fallback owner:** the current OWNER of the repository namespace. The owner
  configured in GitLab is used only when the namespace must first be created.
- **Attribution user:** the active SkillHub account matching the pipeline
  initiator, or the current namespace OWNER when the initiator is absent or has
  no SkillHub identity binding. This user submits the imported version for
  review.
- **Effective skill owner:** the attribution user when a source skill is first
  created; the existing skill container owner for every later version. Pipeline
  initiators do not transfer container ownership.

## Input And Naming Rules

### GitHub URL

The first release accepts only:

```text
https://github.com/<owner>/<repository>
https://github.com/<owner>/<repository>.git
```

The importer rejects:

- non-HTTPS schemes;
- non-`github.com` hosts;
- credentials, ports, query strings, or fragments;
- additional path segments;
- empty owner or repository segments;
- SSH/scp syntax; and
- GitHub Enterprise or other Git hosting providers.

Canonicalization removes a trailing `.git`, lowercases the namespace input,
and preserves the canonical GitHub URL without `.git`.

### Namespace

For `<owner>/<repository>`:

```text
slug         = oss-<owner>-<repository>
display name = OSS-<owner>-<repository>
```

The slug is normalized to lowercase and must pass existing SkillHub namespace
slug validation. Only the fixed display-name prefix is uppercased. The rest of
the display name matches the normalized owner/repository string.

The repository-to-namespace association is durable and unique. The ensure
operation behaves as follows:

- repository already bound to the derived namespace: return `EXISTING`;
- repository bound to another namespace: return conflict;
- derived slug already exists without the same repository binding: return
  conflict and require an administrator to resolve it explicitly;
- namespace absent: resolve the configured fallback owner, create an ACTIVE
  TEAM namespace, assign that account as OWNER, and persist the repository
  binding in one transaction;
- existing namespace is FROZEN, ARCHIVED, GLOBAL, or otherwise non-writable:
  fail without changing it.

The importer never transfers an existing namespace's ownership, rewrites a
customized display name, or changes lifecycle state. After creation, the
namespace's current OWNER is authoritative for fallback attribution and review.

## Identity And Authorization

OAuth lookup uses the values already persisted by the Python OAuth flow:

```text
identity_binding.provider_code = registration id, for example keycloak
identity_binding.login_name    = Keycloak preferred_username
```

`SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_NAME=tsso` is a UI
label and is not an identity lookup key. The provider code remains `keycloak`.

The source-import endpoints require:

- a valid bearer API token;
- token scope `source:import`; and
- importer actor platform role `SKILL_ADMIN` or `SUPER_ADMIN`.

Browser sessions and CSRF are not used on this `/api/cli/` surface. Production
requests must not use mock authentication. The dedicated scope is not added to
ordinary token defaults.

Identity and ownership rules:

1. Resolve the optional pipeline initiator by provider code and login name.
2. If exactly one ACTIVE account is found, use it as the attribution user and
   plan a MEMBER insertion when it is not already a namespace member.
3. If no initiator is supplied or no binding is found, use the current
   namespace OWNER as the attribution user.
4. If a binding resolves to a disabled/non-active account, or identity data is
   ambiguous, fail closed instead of silently falling back.
5. For a new source skill, make the attribution user the skill container owner.
6. For a later version of the same source skill, preserve the existing skill
   container owner and use the current attribution user only as review
   submitter.

The importer actor remains the audit actor. Existing TEAM namespace review
authorization remains authoritative, including namespace-owner review. The
import workflow must separate actor, submitter, and owner instead of reusing one
`publisher_id` for all three concepts.

## Source Discovery And Packaging

The importer operates only inside `CI_PROJECT_DIR` unless an explicit safe
subdirectory override is configured.

- Discover files named exactly `SKILL.md` recursively.
- Ignore `.git` and never follow filesystem symlinks.
- Reject a discovered skill root that resolves outside the checkout.
- Sort skill roots and archive entries deterministically.
- Treat every `SKILL.md` parent directory as one independent skill root.
- When one skill root contains another discovered skill root, exclude the
  descendant skill directory from the ancestor package. The descendant is
  packaged independently.
- Place each root's contents at ZIP root so `SKILL.md` is at archive root.
- Preserve every packaged source file byte-for-byte. Import metadata and a
  missing-version override travel as multipart metadata, not as source-file
  edits.

If no `SKILL.md` exists, fail the job. Removed source paths do not archive,
yank, hide, or delete previously imported SkillHub skills in the first release.

### Version and idempotency

- Preserve an explicit non-empty source `version` exactly.
- If version is missing, request an effective version of
  `git-<CI_COMMIT_SHA>` through a separate `versionOverride` import field.
- Reject a version override when `SKILL.md` already declares a version.
- General CLI/API publishing retains its existing UTC timestamp fallback; only
  this importer supplies the deterministic override.
- The backend computes the authoritative content fingerprint from the original
  extracted package; the importer may compute the same value for its report but
  cannot override the backend value.
- If the same repository/path has the same content fingerprint, return
  `SKIPPED_UNCHANGED`, even when a later repository commit contains unrelated
  changes.
- If an already-bound source path now resolves a different skill slug, fail
  with source-identity drift instead of silently creating a second container.
- If the requested version already exists with the same resulting package
  fingerprint, return `SKIPPED_ALREADY_IMPORTED`.
- If an explicit version already exists with different content, return an
  immutable-version conflict.
- A changed unversioned skill uses the current repository revision as its new
  deterministic `git-<sha>` version.

This prevents pipeline retries and unrelated repository commits from creating
duplicate SkillHub versions.

## Source Provenance

Commit SHA is the canonical locator. Tag or branch is descriptive because refs
can move. GitHub Release title, notes, assets, and publication date are not
available from a Git checkout and are outside the first release.

Ref selection is deterministic:

- non-empty `CI_COMMIT_TAG`: `sourceRefType=TAG` and that tag as `sourceRef`;
- otherwise non-empty `CI_COMMIT_BRANCH`: `sourceRefType=BRANCH` and that branch
  as `sourceRef`;
- otherwise: `sourceRefType=COMMIT` with no source ref. Merge-request or other
  synthetic `CI_COMMIT_REF_NAME` values remain report context and are not
  represented as real GitHub branches.

Persist provenance per imported skill version:

```text
repositoryUrl
repositoryRevisionSha
sourceRefType       TAG | BRANCH | COMMIT
sourceRef           optional tag or branch name
sourcePath
contentFingerprint
```

Use local Python-owned tables rather than adding organization-specific columns
to the upstream-followed `skill_version` table:

- `local_oss_namespace_source`: one-to-one namespace/repository binding with a
  unique canonical repository URL;
- `local_oss_skill_source`: stable repository source-path to skill-container
  binding, unique within its namespace source; and
- `local_oss_skill_version_source`: one-to-one version provenance and digest
  evidence, cascading when the local skill version is durably deleted.

The backend computes browse URLs; it does not trust a caller-supplied deep
link. Example:

```text
https://github.com/mattpocock/skills/tree/<commit-sha>/skills/engineering/code-review
```

Review detail must show the declared repository, ref when present, abbreviated
commit, source path, and exact commit link. Published skill-version detail must
show the same provenance. Pending or rejected versions must not leak through
public reads.

## API Contract

Backend route declarations stay root-relative. A deployment base path is added
by the public proxy, not by FastAPI.

### Ensure namespace

```text
PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}
```

JSON request:

```json
{
  "repositoryUrl": "https://github.com/mattpocock/skills",
  "displayName": "OSS-mattpocock-skills",
  "fallbackOwnerProviderCode": "keycloak",
  "fallbackOwnerLoginName": "platform-owner"
}
```

Response data includes `CREATED|EXISTING`, namespace slug/display name/status,
canonical repository URL, and current owner display identity. It does not make
the pipeline consume the internal user ID.

### Validate one skill

```text
POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate
```

Multipart request contains one unchanged source ZIP plus JSON provenance,
optional `versionOverride`, and optional initiator identity. Validation resolves
identity and namespace context, extracts and validates the package, computes
the authoritative fingerprint, checks fingerprint/version conflicts, and
returns the planned effective owner and outcome. It performs no
database or storage mutation, including no namespace-membership insertion.

### Submit one skill

```text
POST /api/cli/v1/source-imports/{namespaceSlug}/skills
```

The multipart shape matches validation. The backend revalidates rather than
trusting a prior response, then reuses focused publish/storage/scanner/review
workflows. When required, it inserts the attribution user as a namespace MEMBER
in the submission transaction. It persists provenance transactionally with the
version record and records the importer actor separately from owner and
submitter.

Response outcomes:

```text
IMPORTED
SKIPPED_UNCHANGED
SKIPPED_ALREADY_IMPORTED
```

`IMPORTED` includes the coordinate, version, stable skill owner, review
submitter, importer actor, version status, review task when created, and
provenance. Errors use the established envelope and request ID.

## Lifecycle

All imported skills use `PUBLIC` visibility in the first release.

The GitLab job succeeds when every package is accepted or skipped. Acceptance
does not mean immediate publication. New versions continue through the
configured scanner and existing namespace review workflow. Expected statuses
may include `SCANNING`, `PENDING_REVIEW`, or another existing intermediate
status. Only an approved `PUBLISHED` version enters public search, resolve,
download, and catalog reads.

The source-import route must not enable SUPER_ADMIN auto-publish merely because
the importer actor holds that role. It explicitly disables direct publication
for user-selected OSS imports.

## GitLab Importer Delivery

Add a small Python package and console entry point under a focused tooling
directory. It must have unit-testable modules for configuration, URL/naming,
discovery, packaging, API transport, and orchestration.

Provide:

- an importer Dockerfile based on Python 3.12;
- a pinned dependency lock/install contract;
- a reusable GitLab CI YAML template;
- a console command such as `skillhub-oss-import`;
- `--json-report <path>` for a durable CI artifact; and
- clear exit codes for configuration, discovery/validation, authorization,
  network, partial submission, and internal failures.

The GitLab job uses the importer image. It does not copy a Python script into
every OSS mirror and does not install the TypeScript SkillHub CLI.

The orchestration order is:

1. load and validate configuration;
2. verify `CI_COMMIT_SHA == git rev-parse HEAD`;
3. canonicalize source URL and derive namespace;
4. discover and package all skill roots;
5. ensure namespace;
6. call server validation for every package;
7. if any validation fails, submit none and fail with the full validation
   summary;
8. submit all validated packages sequentially;
9. continue after an individual runtime submission failure to collect a full
   report;
10. fail the job if any submission failed; and
11. upload the JSON report as a GitLab artifact.

Already accepted submissions are not rolled back after a later network/runtime
failure. A retry is safe because digest/version outcomes are idempotent.

## Variables Contract

The final Chinese SOP, CI template, importer `--help`, and tests use these exact
names. Operators may map existing organization variables into them in YAML.

### Required SkillHub variables

| Variable | Secret | Meaning |
| --- | --- | --- |
| `SKILLHUB_BASE_URL` | No | Public application base, including `/skillhub` when configured; no trailing API path. |
| `SKILLHUB_API_TOKEN` | Yes | Masked/protected service-account token with `source:import`. |
| `SKILLHUB_SOURCE_REPOSITORY_URL` | No | User-supplied canonicalizable GitHub repository URL. |
| `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` | No | OAuth registration/provider code used only to create a missing namespace, normally `keycloak`. |
| `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME` | No | Fallback namespace owner's Keycloak `preferred_username`. |

### Required CI integration variable

| Variable | Secret | Meaning |
| --- | --- | --- |
| `SKILLHUB_IMPORTER_IMAGE` | No | Immutable importer OCI image reference, pinned by version or digest; never use `latest` in production. |

### Pipeline initiator variables

| Variable | Required | Meaning |
| --- | --- | --- |
| `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` | No | Triggering user's Keycloak `preferred_username`; blank/unmatched falls back to current namespace OWNER for version submission and first-skill ownership. |
| `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` | No | Defaults to `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE`. |

The caller maps organization-specific GitLab/OIDC variables into these names.
The importer does not assume that a human display name, GitLab numeric user ID,
commit author, or `CLIENT_NAME=tsso` is a Keycloak login name.

### GitLab predefined variables

| Variable | Use |
| --- | --- |
| `CI_PROJECT_DIR` | Checkout root. |
| `CI_COMMIT_SHA` | Immutable repository revision and deterministic fallback version. |
| `CI_COMMIT_TAG` | Optional tag ref. |
| `CI_COMMIT_BRANCH` | Optional branch ref. |
| `CI_COMMIT_REF_NAME` | Report context for merge-request or other synthetic refs; not treated as a GitHub branch. |
| `CI_PIPELINE_ID` | Audit/report correlation. |
| `CI_JOB_ID` | Audit/report correlation. |

### Optional runtime variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `SKILLHUB_IMPORT_SOURCE_ROOT` | `CI_PROJECT_DIR` | Safe subdirectory inside the checkout. |
| `SKILLHUB_IMPORT_REPORT_PATH` | `skillhub-oss-import-report.json` | JSON report artifact path. |
| `SKILLHUB_IMPORT_TIMEOUT_SECONDS` | `60` | Per-request timeout. |
| `SSL_CERT_FILE` | unset | Standard CA bundle path for internal PKI when required. |

The first release has no variables for visibility, auto-publish, namespace
status mutation, owner transfer, deletion, or disabling review.

### Example mapping

```yaml
variables:
  SKILLHUB_IMPORTER_IMAGE: "registry.example.com/platform/skillhub-oss-importer:1.0.0"
  SKILLHUB_BASE_URL: "https://skills.example.com/skillhub"
  SKILLHUB_SOURCE_REPOSITORY_URL: "$USER_SELECTED_GITHUB_REPOSITORY_URL"
  SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE: "keycloak"
  SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME: "$PLATFORM_OSS_FALLBACK_OWNER"
  SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE: "keycloak"
  SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME: "$ORGANIZATION_PREFERRED_USERNAME"
```

`SKILLHUB_API_TOKEN` is configured as a masked, protected GitLab CI/CD secret
and is never printed or stored in the JSON report.

## Public Routing And `/skillhub`

FastAPI declares `/api/cli/v1/source-imports/...`. The importer calls the
public application base:

```text
SKILLHUB_BASE_URL=https://skills.example.com/skillhub
request=https://skills.example.com/skillhub/api/cli/v1/source-imports/...
```

The existing gateway/frontend Nginx strips the configured base path and proxies
`/api/...` to `skillhub-server:8080`. This is a reverse proxy, not a browser
redirect. The backend Kubernetes Service remains internal and no second public
host or ingress route is added.

URL composition must preserve a base path and reject a base URL containing
credentials, query, fragment, or an `/api` suffix. Root deployment with an
empty base path remains supported.

## Error And Security Behavior

- Never log the API token or a GitLab repository credential.
- Reject ZIP traversal, symlinks, checkout escapes, invalid UTF-8 frontmatter,
  duplicate paths, package-limit violations, and disallowed source URLs.
- Fail closed on ambiguous, disabled, or duplicate identity resolution.
- Return conflict rather than silently adopting an existing unbound namespace.
- Do not mutate an existing namespace owner, display name, or status.
- Do not bypass scanner/review based on the importer actor's platform role.
- Record request ID, pipeline/job IDs, actor, effective owner, repository,
  review submitter, commit, source path, outcome, and review/version IDs in
  structured audit data.
- JSON reports contain login/display identities but no internal credentials.
- Use deterministic retry-safe outcomes. Network uncertainty after submission
  is resolved by retry/idempotency, not by deleting accepted versions.

## Chinese Deployment And Usage SOP

The implementation must deliver a Traditional Chinese SOP under the deployment
documentation. It covers:

1. database migration and backend/frontend image rollout order;
2. confirmation that PostgreSQL, Redis, object storage, scanner, backend, and
   web proxy are healthy;
3. creation of an importer service account;
4. assignment of the required platform role;
5. creation and rotation of a `source:import` API token;
6. building and publishing the importer image;
7. importing the reusable GitLab CI template;
8. the complete variables table, organization-variable mapping example, and
   masked/protected secret setup;
9. root versus `/skillhub` base URL examples;
10. CA bundle configuration for internal TLS;
11. manually triggering a pipeline with a GitHub URL;
12. interpreting `IMPORTED`, `SKIPPED_*`, validation errors, partial failures,
    scanner status, and namespace-owner review;
13. retry and rollback boundaries;
14. verification commands and a first-import checklist; and
15. token revocation and incident steps.

## Verification Design

Develop test-first and verify each phase before proceeding.

### Importer unit/integration tests

- valid `.git` and non-`.git` GitHub URL canonicalization;
- rejection of hosts, schemes, ports, credentials, query, fragment, extra path,
  SSH syntax, and traversal-like inputs;
- namespace slug/display-name transformation;
- exact `SKILL.md` discovery, no symlink following, containment checks, stable
  order, nested-root exclusion, and no-skill failure;
- deterministic archive and source fingerprint;
- preservation of source frontmatter plus missing-version override behavior;
- ref selection and commit mismatch failure;
- subpath-safe URL construction;
- token redaction, response envelope/error parsing, report output, and exit
  codes;
- validate-all-before-submit behavior;
- skip, retry, and partial-submission reporting.

### Backend tests

- bearer required, `source:import` scope required, platform role required;
- browser/session token, wrong scope, inactive actor, and unauthorized actor;
- provider/login resolution, missing-trigger fallback, disabled/ambiguous
  identity failure, and automatic MEMBER insertion;
- namespace create/bind transaction, existing binding, slug collision,
  repository collision, lifecycle/type rejection, and current-owner fallback;
- validation has no database or storage mutation, including membership;
- effective owner differs from importer audit actor;
- initial owner attribution, stable owner across different later initiators,
  and per-version review submitter attribution;
- provenance persistence and computed GitHub links;
- stable source-path binding, slug identity drift, and cross-path slug
  conflicts;
- unchanged and already-imported skips;
- explicit-version content conflict;
- scanner/review transition with auto-publish disabled;
- transaction rollback, object-storage compensation, request ID, and audit
  detail;
- provenance visibility in review, owner, and public published projections;
- PostgreSQL migration upgrade from the previous baseline.

### Real runtime verification

The feature is not complete with mocks or SQLite-like substitutes. Start and
connect all related services:

- PostgreSQL with the real migration;
- Redis;
- MinIO/S3-compatible storage;
- scanner service and scan consumer;
- Python backend;
- production web/Nginx proxy; and
- importer container acting as a GitLab-like job.

Run a fixture repository containing multiple, nested, unchanged, invalid, and
versioned skills through:

- root public URL;
- `/skillhub` public URL;
- first namespace creation/import;
- unchanged retry;
- changed unversioned skill;
- explicit-version conflict;
- initiator-found and fallback-owner cases;
- scanner/review acceptance; and
- namespace-owner review followed by public resolve/download.

Required gates include focused and full backend tests, importer tests and
package/image build, OpenAPI generation/drift checks, relevant frontend tests,
Kustomize and Compose rendering, production image builds, a real HTTP smoke
through Nginx, and `git diff --check`.

## Non-Goals

- No backend Git clone, GitHub credential handling, webhook, polling, or
  arbitrary URL fetch.
- No GitHub Enterprise, SSH URL, GitLab source, or non-GitHub hosting support.
- No GitHub Release API metadata, release assets, or release-note ingestion.
- No bulk multi-skill backend request or all-packages database transaction.
- No automatic archive/delete/yank/hide when a source skill disappears.
- No namespace owner transfer, lifecycle restore/unfreeze, or display-name
  overwrite.
- No direct publication, scanner bypass, review bypass, or visibility choice.
- No Java, Maven, Spring Boot, or hybrid runtime.
- No TypeScript CLI requirement for the GitLab importer.

## Decisions

- 2026-08-18: Operate on the existing GitLab checkout; do not clone in backend
  or importer.
- 2026-08-18: Accept only GitHub HTTPS repository URLs in the first release.
- 2026-08-18: Derive `oss-owner-repo` and display `OSS-owner-repo`.
- 2026-08-18: Resolve Keycloak users by `provider_code=keycloak` and
  `login_name=preferred_username`; `CLIENT_NAME=tsso` is not an identity key.
- 2026-08-18: Create missing namespaces with a configured fixed owner, then use
  the namespace's current OWNER as the durable fallback.
- 2026-08-18: Attribute a new skill to a resolved pipeline initiator or current
  namespace OWNER, preserve that skill owner for later versions, attribute each
  review submission to the current initiator/fallback, and keep the service
  token principal as audit actor.
- 2026-08-18: Preserve explicit versions and use deterministic Git commit
  versions only when absent; skip unchanged content.
- 2026-08-18: Store commit-first provenance per version and treat refs/releases
  as secondary descriptive data.
- 2026-08-18: Submit imported content through scanner and namespace-owner
  review; pipeline success means accepted/skipped, not immediately published.
- 2026-08-18: Use a Python importer image plus narrow `/api/cli/` endpoints via
  the existing public root or `/skillhub` reverse-proxy entrypoint.
- 2026-08-18: Deliver a complete Traditional Chinese deployment and usage SOP
  with an exact variables contract.
