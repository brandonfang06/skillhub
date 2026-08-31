# SkillHub Security Engineering Guideline

This document defines the security guardrails for every SkillHub feature,
bug fix, integration, and deployment change. It is an engineering checklist,
not a vulnerability disclosure policy or a description of organization
infrastructure.

Use the CIA triad for every change:

- **Confidentiality:** only authorized identities can read protected data,
  credentials, skill content, and operational metadata.
- **Integrity:** identities, lifecycle state, review decisions, packages,
  audit records, and configuration cannot be changed without authorization or
  without detection.
- **Availability:** expected failures, load, retries, and dependency outages do
  not leave the service unavailable or stuck in an invalid state.

## Required Security Review

Before implementation, identify:

1. The data, credentials, actions, and services affected by the change.
2. Every trust boundary crossed by browser, CLI, API, worker, scanner, CI job,
   storage, database, Redis, identity provider, or LLM traffic.
3. Who may perform the action and who must be denied.
4. The invariants that must remain true after success, failure, timeout,
   cancellation, retry, and rollback.
5. The realistic abuse cases, not only the expected user flow.

Record material security decisions in the feature specification or plan. A
change with a new trust boundary, credential, public endpoint, or accepted
risk must not rely on an undocumented assumption.

## Trust Model

- Do not trust client-controlled forwarding headers. Trust
  `X-Forwarded-For`, `X-Real-IP`, and `X-Forwarded-Proto` only when a configured
  ingress replaces them and direct backend access is blocked.
- Test-only identity, authorization, or feature bypasses must be impossible to
  activate through a production request. Prefer dependency injection and test
  fixtures over request headers or runtime backdoors.
- External scanners, LLMs, identity providers, source repositories, object
  storage, and package registries are separate trust boundaries. Validate
  their identity, timeout behavior, response shape, and data exposure.

## Authentication And Authorization

- Deny access by default. Every protected route must resolve identity through
  the shared authentication path and enforce the route-specific policy.
- Authentication proves identity; authorization separately proves permission
  for the requested platform, namespace, skill, version, or administration
  action.
- Cover unauthenticated, authenticated-but-forbidden, allowed, disabled-user,
  expired-token, revoked-token, and wrong-scope cases.
- Browser session, user API token, service token, and device flow are distinct
  principal types. Do not silently broaden one principal type to routes meant
  for another.
- OAuth/OIDC flows must validate state, callback binding, provider identity,
  redirect targets, and replay behavior. State must be single-use, expiring,
  and safe across supported replica counts.
- Cookie-authenticated mutations must enforce the repository's CSRF contract.
  Cookies must be `HttpOnly`, use the narrowest path, and be `Secure` in HTTPS
  deployments.
- Local registration, local login, bootstrap accounts, session bootstrap, and
  debug authentication must be explicit deployment decisions. UI hiding is
  not endpoint protection.
- Password reset, login, device authorization, and token creation endpoints
  require replay protection, bounded attempts or rate limiting, expiration,
  and non-enumerating errors.
- Tokens must be random, stored as hashes, shown only at creation, scoped to
  minimum permissions, revocable, and time-limited unless a documented
  operational requirement justifies otherwise.

## Skill And Package Integrity

SkillHub distributes instructions and executable content. Treat every skill
package as untrusted, including packages from authenticated employees and
approved source repositories.

- The package that was scanned, reviewed, approved, published, and downloaded
  must be the same immutable content. Bind stages using a cryptographic digest
  or immutable source revision rather than a mutable branch name alone.
- Scanner success is supporting evidence, not proof of safety. Preserve human
  review where governance requires it, and show partial or failed analyzer
  results to reviewers.
- Reviewers must be able to inspect visibility, provenance, changed files,
  relevant scan evidence, and the exact version being approved.
- Enforce archive size, extracted size, file count, single-file size, path
  normalization, duplicate-path, extension, and required-metadata limits
  before persistence or scanning.
- Never extract an archive outside a dedicated contained directory. Reject
  absolute, parent-relative, drive-qualified, ambiguous, and unsafe link paths.
- Render uploaded Markdown, HTML-like content, SVG, and code as untrusted
  input. Sanitize active content and use attachment disposition when inline
  rendering is unnecessary.
- Download and file-read authorization must be enforced by the backend for
  every route alias. Frontend visibility is not access control.
- Published versions are immutable. Lifecycle pointers such as
  `latest_version_id` must never bypass status and visibility checks.
- Preserve provenance and content fingerprints in read, download, import, and
  audit flows. Do not claim a package was scanned when only a mutable source
  reference was scanned.

## Data Confidentiality

- Classify user identity data, analytics, IP addresses, user agents, source
  code, package files, credentials, audit details, and scanner findings before
  adding storage or exports.
- Collect only data required by the feature. Define retention and deletion
  behavior for new personal or operational data.
- A skill may accidentally contain secrets, internal URLs, source code, or
  proprietary documents. Do not send package content to an external scanner
  or LLM without an explicit deployment setting and documented data boundary.
- Do not log passwords, session IDs, reset codes, raw tokens, authorization
  headers, credentialed URLs, package contents, or provider secrets.
- Redact secrets from errors, job logs, Git remotes, command arguments,
  reports, analytics, and audit details.
- Exports opened by spreadsheet software must neutralize formula prefixes and
  enforce row, time-range, and authorization limits.
- Do not place secrets in ConfigMaps, images, frontend bundles, generated
  runtime JavaScript, example values used unchanged in production, or Git.

## Mutation And Audit Integrity

- Mutating endpoints require authorization, an authenticated audit actor,
  idempotency where retries are possible, a clear transaction boundary, and
  rollback or compensation coverage.
- Publish external side effects only after the database transaction commits.
  Define retry or reconciliation when a post-commit notification, queue, scan,
  search, or storage action fails.
- Validate current state and authorization in the same transaction as the
  mutation when concurrent changes could invalidate the decision.
- Audit privileged reads and security-relevant mutations with actor, action,
  target, timestamp, request ID, and outcome. Do not treat spoofable client
  metadata as authenticated identity.
- Audit storage should be access-controlled and included in backup and
  retention plans. State explicitly when logs are not tamper-evident.

## External Calls And Secrets

- Follow the approved transport contract for each client. The OSS SkillHub CLI
  registry may use an operator-configured internal HTTP URL when the
  organization CA cannot be installed in the CLI runtime; do not silently
  rewrite it to HTTPS or redirect it. Do not generalize this CLI-specific
  exception to unrelated integrations.
- Apply explicit connect, read, write, and total timeouts. Bound retries, use
  backoff, and retry only operations that are safe or idempotent.
- Validate remote URLs by scheme, host, port, user-info, query, fragment, and
  redirect behavior. Prevent SSRF to loopback, link-local, metadata, and
  unintended internal addresses.
- Validate external response status, content type, size, and schema before
  using it in authorization, lifecycle, or scan decisions.
- Service credentials must have the smallest scope, short practical lifetime,
  rotation procedure, and revocation procedure. CI artifacts containing
  credentials must have restricted access and bounded retention.
- Pin release artifacts to immutable versions or digests. Floating image tags
  are not acceptable evidence of what was deployed.

## Availability And Failure Safety

- Bound request bodies, pagination, exports, archive expansion, scanner work,
  background queues, database queries, and concurrent external calls.
- Rate-limit authentication, reset, device, upload, download, search, export,
  and expensive administration paths according to deployment needs.
- A timeout or dependency failure must reach a visible terminal or retryable
  state. Do not leave skill versions permanently in `SCANNING` or another
  transitional state.
- Prevent retry storms and duplicate side effects. Use leases, idempotency,
  dead-letter or reconciliation behavior, and observable retry counts where
  appropriate.
- Define the effect of PostgreSQL, Redis, object storage, scanner, identity
  provider, LLM, and notification outages. Shared dependencies must not create
  undocumented correlated failure modes.
- Production manifests require resource requests and limits, health probes,
  controlled rollout behavior, and an explicit replica and disruption model.
- Database, object storage, configuration, and required audit data need tested
  backup and restore procedures with documented RPO and RTO.

## Verification Requirements

Unit tests are necessary but not sufficient for security-sensitive changes.

- Add negative tests before or alongside the implementation.
- Test every route alias and principal type affected by the change.
- Test malformed, oversized, replayed, concurrent, expired, revoked,
  unauthorized, and dependency-failure scenarios.
- Use real PostgreSQL, Redis, object storage, scanner, proxy, and browser flows
  when the changed behavior depends on those services. Mocks supplement but do
  not replace runtime verification.
- Verify both root and configured subpath deployments for browser, OAuth,
  cookie, redirect, API, and download changes.
- Inspect logs and audit rows to ensure failures are diagnosable without
  exposing secrets.
- Render deployment manifests and verify the effective environment, secret
  references, image versions, TLS path, ingress policy, and network reachability.
- Review the complete diff from a fixed merge base before merge. Re-evaluate
  interactions with auth, lifecycle, visibility, scanner, import, storage,
  analytics, and deployment even when focused tests pass.

## Completion Checklist

A feature is not ready to merge until the author or reviewer can answer:

- **C:** What protected data is read, stored, logged, exported, or sent across
  a trust boundary, and why can no unauthorized principal access it?
- **I:** How do we prove the actor, authorization, state transition, audit
  record, and artifact identity are correct under retries and concurrency?
- **A:** What happens on timeout, overload, dependency failure, restart, and
  partial completion, and how does the system recover?
- Which abuse cases and negative paths were tested with the real services that
  define the behavior?
- What deployment setting, accepted risk, or operational follow-up remains,
  and where is it documented?
