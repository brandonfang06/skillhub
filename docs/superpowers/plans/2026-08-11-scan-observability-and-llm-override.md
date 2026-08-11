# Scan Observability and LLM Failure Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist trustworthy partial-scan evidence, expose a narrow platform-admin override, and provide an end-to-end scan timeline without weakening normal review controls.

**Architecture:** A guarded scanner 1.0.2 backport exposes analyzer completion and stable LLM failure codes. The backend runs baseline and enhanced stages, stores execution metadata in an organization-owned extension table, and evaluates approval through a fail-closed policy module. The review UI renders partial evidence and requires an explicit reason and confirmation from a platform reviewer.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL, Redis Streams, React, TypeScript, TanStack Query, Vitest, Playwright, Docker.

---

### Task 1: Guarded scanner failure contract

**Files:**
- Create: `scanner/backports/apply_1_0_2_llm_failure_backport.py`
- Modify: `scanner/Dockerfile`
- Modify: `server-python/tests/test_scanner_image_contract.py`
- Create: `server-python/tests/test_scanner_llm_failure_backport.py`

- [ ] Write tests that apply the backport to an exact 1.0.2 source fixture and assert timeout, unavailable, and generic failures propagate as sanitized markers while `analyzers_used` is included in `ScanResponse`.
- [ ] Run `uv run pytest tests/test_scanner_image_contract.py tests/test_scanner_llm_failure_backport.py -q` and confirm the new assertions fail before implementation.
- [ ] Implement exact-count replacements guarded by `cisco_ai_skill_scanner-1.0.2.dist-info`; do not include provider exception text in the raised marker.
- [ ] Invoke the new script during image construction after the existing base-URL backport and remove both temporary scripts.
- [ ] Re-run the targeted tests and build `skillhub-scanner:llm-override-verify`.

### Task 2: Durable local scan-execution evidence

**Files:**
- Create: `server-python/app/db/local_migration/20260811_01__local_security_scan_execution.sql`
- Modify: `server-python/tests/test_schema_migration_baseline.py`
- Modify: `server-python/app/publish/scanner_result.py`
- Modify: `server-python/app/publish/scan_worker.py`
- Modify: `server-python/app/security_audit.py`
- Modify: `server-python/tests/test_publish_scanner_result.py`
- Modify: `server-python/tests/test_security_audit_read.py`

- [ ] Add failing migration contract tests for the local identifier, foreign-key cascade, status constraint, and JSON defaults.
- [ ] Add failing persistence/read tests for `PENDING`, `COMPLETE`, `PARTIAL`, and `FAILED` evidence without changing the upstream `security_audit` schema.
- [ ] Create `local_security_scan_execution` keyed by `security_audit_id` with normalized status, requested/completed analyzers, failures, failure code, and timestamps.
- [ ] Upsert execution evidence in the same transaction as audit/version state changes; terminal scan failure must also write `FAILED` evidence.
- [ ] Left-join the extension in security-audit reads and derive legacy rows as `PENDING` or `COMPLETE` when no extension row exists.
- [ ] Run the targeted migration, scan-result, worker, and read tests.

### Task 3: Two-stage scanner client and failure classification

**Files:**
- Modify: `server-python/app/publish/scanner_client.py`
- Modify: `server-python/tests/test_publish_scanner_client.py`

- [ ] Add failing tests proving non-LLM scans remain one request, LLM scans run baseline then enhanced, enhanced success is authoritative, and baseline options disable only LLM/meta.
- [ ] Add failing tests proving only backend read timeout and exact `LLM_TIMEOUT`/`LLM_UNAVAILABLE` markers yield `PARTIAL`; generic 429/5xx and unknown LLM errors must raise.
- [ ] Add failing compatibility tests proving upload options are sent as both query and multipart fields and older scanner responses remain readable.
- [ ] Implement a pure normalized failure classifier and a stage request helper; never inspect broad HTTP status alone.
- [ ] Populate requested/completed/failure evidence from configured options and scanner-reported `analyzers_used`.
- [ ] Run the complete scanner-client test module.

### Task 4: Structured scan lifecycle logging

**Files:**
- Modify: `server-python/app/publish/scanner_handoff.py`
- Modify: `server-python/app/publish/scanner_client.py`
- Modify: `server-python/app/publish/scan_consumer.py`
- Modify: `server-python/app/publish/scan_worker.py`
- Modify: `server-python/tests/test_publish_orchestration.py`
- Modify: `server-python/tests/test_publish_scan_consumer.py`
- Modify: `server-python/tests/test_publish_scan_worker.py`

- [ ] Add failing `caplog` assertions for stable enqueue, start, stage, retry, completion, and terminal-failure event names plus task/version/retry/message context.
- [ ] Add elapsed milliseconds, normalized failure code, resulting audit/version state, and newly created retry message ID where available.
- [ ] Keep logs parameterized and exclude payloads, credentials, provider response bodies, findings, and skill content.
- [ ] Run the orchestration, consumer, worker, and scanner-client logging tests.

### Task 5: Fail-closed review approval policy

**Files:**
- Create: `server-python/app/review/scan_approval.py`
- Modify: `server-python/app/review/approval.py`
- Modify: `server-python/app/review/batch.py`
- Modify: `server-python/app/api/reviews.py`
- Create: `server-python/tests/test_review_scan_approval.py`
- Modify: `server-python/tests/test_review_approve.py`
- Modify: `server-python/tests/test_review_batch.py`

- [ ] Add failing pure policy tests for no audit, complete, pending, failed, eligible partial, forbidden namespace reviewer, missing confirmation/reason, non-LLM failure, missing static evidence, and high/critical baseline findings.
- [ ] Add failing transaction tests proving denied attempts perform no review/version/skill/audit/search/notification writes.
- [ ] Extend the approval request with `confirmScanOverride` and `scanOverrideReason`; read platform roles once and evaluate the latest locked audit evidence before mutations.
- [ ] Write `REVIEW_APPROVE_SCAN_OVERRIDE` with normalized evidence and reason only for a valid partial override; preserve ordinary approval behavior otherwise.
- [ ] Mark batch approval inputs as override-ineligible so partial rows return an individual-review-required result while other rows retain partial-success behavior.
- [ ] Run the review policy, route, transaction, and batch tests.

### Task 6: Reviewer evidence and explicit override UI

**Files:**
- Modify: `web/src/features/security-audit/types.ts`
- Modify: `web/src/features/security-audit/security-audit-section.tsx`
- Modify: `web/src/features/security-audit/security-audit-section.test.tsx`
- Create: `web/src/features/review/scan-override-dialog.tsx`
- Create: `web/src/features/review/scan-override-dialog.test.tsx`
- Modify: `web/src/pages/dashboard/review-detail.tsx`
- Modify: `web/src/pages/dashboard/review-detail.test.tsx`
- Modify: `web/src/features/review/use-review-detail.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [ ] Add failing rendering tests for complete, partial-platform, partial-namespace, scanning, and failed states.
- [ ] Add failing interaction tests requiring both checkbox and trimmed reason before a platform reviewer can submit a partial override.
- [ ] Extend audit types and approval transport without manually editing generated OpenAPI output.
- [ ] Show completed/failed analyzers and an amber incomplete warning; disable namespace approval and all `SCAN_FAILED` approval; keep rejection available.
- [ ] Keep the existing normal confirmation dialog for complete scans and submit override fields only from the dedicated dialog.
- [ ] Run the targeted Vitest modules, typecheck, lint, and production build.

### Task 7: Real runtime and regression verification

**Files:**
- Create: `docs/backend-python-maintenance/results/2026-08-11-scan-observability-and-llm-override.md`

- [ ] Apply migrations to a real PostgreSQL container and verify the local extension table plus legacy-read fallback.
- [ ] Run a real Redis consumer flow that persists `PARTIAL`, then exercise valid and denied approval paths against PostgreSQL and verify audit, notification, visibility, and search state.
- [ ] Run the built scanner container against a controlled unavailable/slow LLM endpoint; prove baseline findings survive and the backend reaches `PENDING_REVIEW` rather than remaining `SCANNING`.
- [ ] Start the complete release stack and use an authenticated browser to verify root and `/skillhub` desktop/mobile review states and that complete scans remain unchanged.
- [ ] Run full backend and frontend suites, scanner image build, backend image build, Kustomize render, release Compose render, and `git diff --check`.
- [ ] Record exact commands, counts, runtime evidence, residual risks, and changed-file scope in the result document.
- [ ] Perform a final code-review pass focused on authorization bypass, state races, retry behavior, migration rollback/upgrade safety, sensitive logging, custom scanner compatibility, and root/subpath regressions.

### Task 8: Prepare the reviewed change for user-authorized integration

**Files:**
- Review all paths changed by Tasks 1-7.

- [ ] Confirm the four known unrelated untracked files and any unrelated worktree changes remain untouched.
- [ ] Run `git status --short`, `git diff --check`, and inspect the complete diff against `07570245`.
- [ ] Stop before staging, committing, merging, or pushing and report the exact verification evidence and any residual risk to the user.
