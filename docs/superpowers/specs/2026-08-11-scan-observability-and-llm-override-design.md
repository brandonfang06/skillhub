# Scan Observability and LLM Failure Override Design

Date: 2026-08-11

## Problem

SkillHub currently treats the scanner HTTP request as one indivisible result.
The bundled scanner runs static, behavioral, and LLM analyzers sequentially, so
an LLM timeout returns HTTP 500 and discards the already-computed non-LLM
findings. The backend eventually changes the version to `SCAN_FAILED`, but its
logs do not provide one consistent task-level timeline. Review approval also
blocks `SCANNING` but does not explicitly reject or audit `SCAN_FAILED`.

## Goals

- Make every scan traceable in backend logs from queue handoff through terminal
  database state.
- Preserve static and behavioral evidence when the optional LLM stage times out
  or is unavailable.
- Allow an explicitly authorized reviewer to approve only a narrowly defined,
  auditable partial scan.
- Keep complete scan behavior, root deployment, and `/skillhub` deployment
  compatible.

## Non-Goals

- Allowing arbitrary scanner failures to be bypassed.
- Letting namespace reviewers or batch review bypass incomplete scans.
- Logging skill contents, findings snippets, credentials, provider responses,
  or other sensitive payloads.
- Forking or carrying an unbounded modification of the third-party scanner
  package.

## Chosen Approach

The backend scanner client performs two stages when LLM analysis is enabled:

1. A baseline request runs all configured non-LLM analyzers and disables LLM
   and meta analysis.
2. An enhanced request runs the normal configured analyzer set, including LLM.

When both requests succeed, the enhanced response remains authoritative. When
the baseline succeeds and the enhanced request ends in an allowlisted LLM
timeout or availability failure, the baseline response is persisted as a
`PARTIAL` audit. Unknown enhanced-stage failures still use the existing retry
and eventual `SCAN_FAILED` path. A baseline failure is never overridable.

This duplicates some analyzer work, but only when LLM is enabled. The upstream
1.0.2 scanner currently catches every LLM exception and returns an empty finding
list, which is indistinguishable from a successful LLM result. The scanner
image therefore applies a version-locked build-time backport using the existing
guarded backport mechanism. It makes LLM failures propagate as sanitized stable
codes and includes the scanner's existing `analyzers_used` value in the API
response. Exact source-count checks make an upstream package change fail the
image build instead of silently applying the patch to incompatible code.

The upload client sends analyzer options in both query parameters and multipart
fields. The upstream 1.0.2 endpoint binds query parameters, while existing
custom endpoints may bind form fields; sending both preserves compatibility.

## Scan Evidence

An organization-owned `local_security_scan_execution` table extends each
`security_audit` row with the following durable fields:

- `scan_status`: `PENDING`, `COMPLETE`, `PARTIAL`, or `FAILED`.
- `analyzers_requested`: JSON array of normalized analyzer identifiers.
- `analyzers_completed`: JSON array of analyzers with usable results.
- `analyzer_failures`: JSON array containing only normalized analyzer and
  failure-code pairs.
- `failure_code`: a normalized terminal failure code when the complete scan is
  unavailable.

The extension is stored under `app/db/local_migration` rather than consuming an
upstream Flyway version or adding collision-prone local columns to an upstream
table. No raw exception or provider response is stored. Existing verdict,
severity, findings, duration, and scanned time fields remain authoritative for
completed evidence. For `PARTIAL`, they describe the successful baseline only.

## Failure Classification

Only these enhanced-stage outcomes can become `PARTIAL`:

- scanner response containing the exact backported `LLM_TIMEOUT` marker;
- scanner response containing the exact backported `LLM_UNAVAILABLE` marker.

Generic backend read timeouts and HTTP 429/5xx statuses are not enough because
they can indicate scanner or proxy failure rather than LLM failure. All
non-allowlisted errors remain retryable scan failures. Failure codes exposed to
the UI are stable values such as `LLM_TIMEOUT` and `LLM_UNAVAILABLE`; raw
exception messages are neither persisted nor returned by the scanner API.

## Lifecycle

- Publish creates the review task and `PENDING` audit, then sets the version to
  `SCANNING` as today.
- A complete result transitions `SCANNING` to `PENDING_REVIEW` or `UPLOADED`
  according to requested visibility.
- An eligible partial LLM result transitions a public or namespace version to
  `PENDING_REVIEW`, preserving baseline findings for review.
- An eligible partial result for a private version follows the existing private
  path to `UPLOADED`; it is not published and therefore needs no review override.
- A baseline failure or non-allowlisted failure reaches `SCAN_FAILED` after the
  existing bounded retries.
- Approval always rejects `SCANNING` and `SCAN_FAILED`.

No new skill-version status is introduced. Scan completeness belongs to the
security-audit record, not the version lifecycle.

## Override Policy

An approval requires scan override when the latest active audit is `PARTIAL`.
The backend permits it only when all conditions hold:

- the reviewer has `SKILL_ADMIN` or `SUPER_ADMIN`;
- `confirmScanOverride` is true;
- `scanOverrideReason` is non-empty;
- all analyzer failures are LLM-related and use an allowlisted failure code;
- `static_analyzer` is present in the completed analyzer evidence;
- baseline `max_severity` is neither `HIGH` nor `CRITICAL`.

Namespace reviewers can inspect the evidence but cannot override it. Batch
approval never accepts scan override and returns an individual-review-required
error for partial scans.

A successful override writes `REVIEW_APPROVE_SCAN_OVERRIDE` instead of the
ordinary approval audit action. Its structured detail contains the audit ID,
normalized failure codes, completed analyzers, baseline severity, and reviewer
reason. Normal approval authorization, self-review rules, optimistic locking,
notification, visibility, and search-index behavior remain unchanged.

## API and UI

Security-audit responses expose `scanStatus`, `analyzersRequested`,
`analyzersCompleted`, `analyzerFailures`, and `failureCode`.

The review page shows an amber incomplete-scan warning with completed and failed
analyzers. For authorized platform reviewers, approval opens a dedicated risk
confirmation requiring both a checkbox and reason. Namespace reviewers see the
warning with approval disabled. Complete scans continue using the normal
approval dialog.

The approval request adds optional `confirmScanOverride` and
`scanOverrideReason` fields. Sending those fields for a complete scan has no
effect and does not change the ordinary audit action.

## Backend Logging

Use parameterized Python logs with stable event names:

- `scan.task.enqueued`
- `scan.task.started`
- `scan.stage.started`
- `scan.stage.completed`
- `scan.stage.failed`
- `scan.task.retry_scheduled`
- `scan.task.completed`
- `scan.task.failed`

Where available, events include `request_id`, `task_id`, Redis message ID,
version ID, scanner type, retry count, stage, elapsed milliseconds, HTTP status,
normalized failure code, audit ID, verdict, finding count, and previous/new
version status. Retriable failures log at warning; terminal failures log at
error; normal lifecycle events log at info.

The backported scanner emits only the analyzer name and normalized failure code
for an LLM failure. Provider response bodies, credentials, skill contents, and
finding snippets are not logged.

## Verification

- Unit tests for failure classification, two-stage requests, logging fields,
  state transitions, and override policy.
- Transaction tests for authorization, optimistic locking, audit detail,
  notifications, search indexing, rollback, and batch rejection.
- Real PostgreSQL and Redis integration for partial and terminal scan states.
- A real scanner-container timeout scenario using a controlled unavailable LLM
  endpoint while baseline analyzers complete.
- Authenticated Playwright desktop/mobile checks for normal, partial-platform,
  partial-namespace, and `SCAN_FAILED` review states under root and `/skillhub`.
- Full backend/frontend suites, typecheck, lint, production build, scanner image
  build, Kustomize render, Compose render, and `git diff --check`.
