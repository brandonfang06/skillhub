# Java Parity Checklist

Use this checklist for every Java -> Python migration milestone. The goal is to prevent shallow
green tests from hiding behavior drift in API shape, authorization, transactions, audit fields,
storage side effects, or lifecycle state.

Do not edit `server/` while using this checklist. Java is a read-only reference.

## Required Plan Section

Every milestone plan must include a `Java Parity Checklist` section before implementation starts.
For each item, mark one of:

- `covered`: implemented and tested in this milestone.
- `not applicable`: explain why the route/helper does not touch that concern.
- `deferred`: explain why it is outside this milestone and name the future milestone or blocker.

Do not use `unknown` for a route ownership change. If the Java behavior is unknown, keep the route
Java-owned and investigate first.

## Required Result Section

Every result document must include the final checklist outcome:

- Java reference files inspected.
- Parity items covered by tests.
- Parity items deferred with rationale.
- Any reviewer feedback accepted/rejected.
- Whether unresolved gaps block route ownership.

Do not move route ownership when parity gaps are unresolved for the route being moved.

## Triage

Classify each finding before changing code:

- Must fix now: correctness, security, API contract, data integrity, migration parity, or test gaps
  that affect the current milestone.
- Defer: broad refactors, performance cleanup, future backend abstractions, or work outside the
  current route/helper boundary.
- Needs evidence: reviewer claims or assumptions that do not match the current code path. Add a
  focused test or document why the current code already covers the risk.

## Java Reference Sources

List the Java controller, service, repository, domain model, and config files used as reference.
At minimum, inspect the Java files that own:

- HTTP route binding and response status.
- service workflow and transaction boundary.
- authorization/session context.
- repository queries or JPA entity defaults.
- storage/scanner/audit side effects.

Record the exact Java class names in the plan/result, for example controller, service, repository,
or entity names. Do not rely only on memory or prior chat context.

## API Contract Parity

Check and test:

- HTTP method, path, query params, headers, and request body parsing.
- Response status codes, envelope/plain JSON mode, field names, pagination shape, and sorting.
- Error status and message compatibility for representative negative cases.
- Request id propagation and response headers when the route uses the SkillHub envelope.
- Vite proxy route ownership, including method-colliding paths.

## Authorization And Session Parity

Check and test:

- Anonymous vs authenticated behavior.
- `X-Mock-User-Id` local development behavior where currently used.
- platform role checks, namespace role checks, owner/admin/auditor differences.
- OAuth/session/API token/CSRF behavior if the route touches those surfaces.

If auth behavior is not fully planned, keep protected mutations Java-owned.

## Database Transaction Atomicity

Check and test:

- Whether Java uses one transaction or separate transactions.
- Which DB writes must commit or roll back together.
- Whether Python holds one `engine.begin()` around the same critical writes.
- What happens when storage/scanner/side effects fail mid-flow.
- Whether cleanup/compensation is required and tested.

For mutations, add a focused failure-path test that proves later DB writes do not happen after a
critical failure.

## Audit Actor And Timestamp Fields

Check and test fields such as:

- `created_by`
- `updated_by`
- `deleted_by`
- `submitted_by`
- `actor_user_id`
- `created_at`
- `updated_at`
- `deleted_at`
- request id, client IP, user agent, and detail JSON.

When Java updates an audit actor field, Python must update the same field unless the milestone plan
explicitly documents a contract change.

## Storage And Side Effects

Check and test:

- local/MinIO/S3 object keys and path traversal safety.
- file metadata rows and object writes.
- bundle zip entry names and bytes.
- scanner task payloads, security audit defaults, and review task creation.
- event/audit/log side effects.
- compensation behavior for after-commit cleanup failures.

If only local storage is implemented, mark MinIO/S3 as deferred and keep production ownership or
route ownership aligned with that limitation.

## Live Verification Evidence

For route migrations, result documents must record:

- direct Java reference call result.
- direct Python call result.
- Vite proxy call result.
- fields compared and fields intentionally ignored.
- Windows live gate command and exact pass/fail output.

For foundation helpers with no route ownership, result documents must record the live gate that
proves affected Java-owned routes still reach Java.

## Deferral Rules

Deferral is allowed only when it does not affect the current route/helper ownership.

Acceptable deferrals:

- MinIO/S3 abstraction while no production publish route is Python-owned.
- OAuth/session/API token behavior while those routes remain Java-owned.
- broad ORM/Alembic migration until Group H.
- performance-only cleanup that does not change behavior.

Unacceptable deferrals:

- missing audit actor fields for a mutation helper used by the current milestone.
- unknown transaction behavior for a route ownership move.
- untested authorization behavior for a protected route.
- storage failure paths for a route that writes DB rows and objects.
