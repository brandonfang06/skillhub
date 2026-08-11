# Scan Observability And LLM Override Verification

Date: 2026-08-11

## Scope

- Preserve completed static and behavioral scan evidence when the scanner reports the exact optional LLM timeout or unavailable marker.
- Keep generic scanner, transport, staging, and malformed-response failures on the bounded retry and `SCAN_FAILED` path.
- Allow only `SKILL_ADMIN` and `SUPER_ADMIN` reviewers to approve an eligible partial scan through an individual, explicitly confirmed override with a non-empty reason.
- Keep namespace reviewers, batch approval, incomplete baseline scans, and HIGH or CRITICAL findings fail-closed.
- Add structured backend logs for task, stage, retry, terminal failure, request correlation, elapsed time, and failure code without logging skill content, provider responses, or arbitrary Redis fields.

## Safety Properties

- The scanner runs a baseline stage before the LLM-enabled stage. A partial result is created only for exact `SKILLHUB_LLM_ANALYSIS_FAILED:LLM_TIMEOUT` or `LLM_UNAVAILABLE` JSON detail values.
- Reported analyzer evidence must be a list and include every requested analyzer. Responses that omit the field entirely retain compatibility with pre-evidence scanner versions.
- Approval checks both aggregate maximum severity and each finding severity before permitting an override.
- Scan result and terminal-failure state transitions are conditional on `SCANNING`, protected by a PostgreSQL advisory transaction lock, and persisted with execution evidence.
- Redis messages are acknowledged only after a successful database commit. Processing failures roll back before retry scheduling or a separately committed terminal transition.
- A message observed before its publish transaction is visible is requeued with the same retry count, avoiding the normal 120-second reclaim delay without spending scanner retry budget.
- Visibility retries preserve the original creation time and use a separate count, capped at 30 attempts or two minutes. Messages beyond the limit remain in the Redis pending list for the existing 120-second reclaim cycle, avoiding both message loss and an infinite hot loop.
- The consumer preserves the Redis `XAUTOCLAIM` cursor across daemon iterations, so a large parked PEL prefix cannot starve later recoverable messages.
- A terminal failure transaction reacquires the scan advisory lease. If a duplicate worker is scanning, the failed message remains pending and cannot overwrite the competing result with `SCAN_FAILED`.
- Override approval writes `REVIEW_APPROVE_SCAN_OVERRIDE` with native JSON audit detail. Duplicate approval remains idempotently rejected and does not duplicate audit or notification rows.

## Verification

- TDD review-finding suite reproduced failures for pre-commit ACK, commit failure, missing analyzers, malformed evidence, unsafe finding severity, loose marker matching, staging failure, terminal lease races, permanent publish rollback, and stale fixture wiring.
- Final focused scan suite: `39 passed`, including real PostgreSQL and Redis delayed commit, commit after the visibility limit, permanent rollback, duplicate-worker terminal races, multi-page reclaim cursor progression, advisory-lock contention, terminal-state guards, request correlation, and timeout persistence.
- Full backend suite against real PostgreSQL and Redis: `1329 passed, 7 warnings`. The final pre-commit rerun completed in 225.67 seconds.
- Ruff passed for every changed Python file. The repository-wide ruff baseline still has 392 unrelated findings in untouched files.
- Frontend typecheck and lint passed; `211` test files and `843` tests passed; the production Vite build passed.
- Logged-in browser verification covered the partial-scan evidence, role-gated override dialog, confirmation and reason validation, desktop and mobile viewports, and horizontal overflow. No browser errors remained.
- A real PostgreSQL override changed the review to `APPROVED`, version to `PUBLISHED`, retained partial scan evidence, wrote one JSON audit record, one notification, and the search document. A duplicate approval changed no counts.
- The rebuilt backend image `skillhub-server-python:scan-llm-override-final-verify` (`sha256:a53c05133c1a...`) started migrations and the Redis consumer, and returned HTTP 200 from `/api/v1/health`.
- A dedicated image-level Redis stream acknowledged an invalid message with zero pending entries while logs omitted the injected secret field.
- The final image parked a permanently absent version with `scan.task.not_ready_parked`, `XPENDING=1`, and `XLEN=1`; it neither lost nor duplicated the message.
- An image-level reclaim test started with 11 pending entries and `reclaim_count=1`; the recoverable 11th entry was reached across cursor pages, recognized as finalized, acknowledged, and reduced pending count to 10.
- The real scanner returned `PARTIAL` with `LLM_UNAVAILABLE` and completed static/behavioral evidence for the exact marker. A generic real `ReadTimeout` produced no overridable failure code.
- Scanner image build, backend image build, generated review OpenAPI byte-for-byte reproduction, `kubectl kustomize deploy\\k8s\\base`, release Compose config, and `git diff --check` passed.
- `web/pnpm-lock.yaml` was restored byte-for-byte to the HEAD blob after the local pnpm 11 executable attempted a generated lockfile rewrite.
- During the final pre-commit rerun, Docker Desktop stopped and caused 17 connection-refused integration failures. After restarting the daemon and applying the local migration to the canonical test database, all 17 affected PostgreSQL/Redis tests passed, followed by the complete `1329 passed` backend rerun.

## Review Result

The deep reviews found message-loss, delayed-commit, staging, analyzer-evidence, finding-severity, marker-matching, log-privacy, terminal lease-race, permanent orphan-message, reclaim-cursor starvation, and fixture-wiring risks. These findings were reproduced with tests and fixed. No known blocker remains for commit and push after the final read-only review.

The runtime remains at-least-once: if Redis retry creation succeeds but acknowledgment fails, both the original and retry message can be observed. Advisory locking and conditional state transitions make that duplicate delivery safe and prevent duplicate scan state changes.
