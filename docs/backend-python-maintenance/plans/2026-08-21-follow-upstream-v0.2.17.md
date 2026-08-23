# Upstream v0.2.17 Python-Only Follow-Up Plan

Date: 2026-08-21

## Objective

Adopt the applicable behavior and contracts from upstream SkillHub `v0.2.17`
without changing the local architecture: FastAPI/Python backend, Python-owned
PostgreSQL migrations, React frontend, TypeScript CLI, Python scanner, and the
existing Compose/Kustomize/plain-manifest deployment paths.

This is an execution handoff. It does not authorize implementation, commits,
pushes, releases, deployments, or pull requests.

## Approved Risk-First Execution Order

Approved on 2026-08-23. Each batch has its own focused and real-service
acceptance gate. Passing a batch does not replace the final integrated-system
gate.

1. **Baseline and contract freeze.** Start from current `origin/dev` in an
   isolated worktree. Record clean backend/frontend baselines, then write and
   observe failing tests for the confirmed behavior gaps.
2. **Correctness and operational safety.** Fix scan-task publication after
   PostgreSQL commit, bearer-token star/unstar/rating access, private
   confirm-publish search/notification effects, and the Aliyun stop command.
   Verify with real PostgreSQL, Redis, and scanner/consumer services.
3. **Compliance feature.** Add immutable `x-astron-compliance` ingestion,
   persistence, API/search/review projections, generated OpenAPI types, and
   three-locale frontend behavior. Reuse `parsed_metadata_json`; no migration.
4. **Administrator namespace governance.** Add the separate session-only
   SUPER_ADMIN namespace management API and page by composing existing Python
   governance workflows. Keep `/admin/namespace-analytics` unchanged.
5. **Integrated-system acceptance.** Start PostgreSQL, Redis, MinIO, scanner,
   Python backend, and production web together. Run migrations and complete
   backend/frontend/CLI suites, image builds, Compose/Kustomize rendering, and
   browser smoke for both `/` and `/skillhub`. Record exact evidence before
   requesting merge authorization.

Implementation may proceed through these five gates, but commit, push, merge,
deployment, release, and PR actions still require explicit user authorization.

## Upstream Release Evidence

- Release: [`SkillHub v0.2.17`](https://github.com/iflytek/skillhub/releases/tag/v0.2.17)
- Published: `2026-08-21T10:13:00Z`
- Tag object: `e74b27debbb1d3f4f6e56c500191bea3487b50eb`
- Tag commit: `15ce199e1a951fed05139e4c984150ddfc45def3`
- Compare: <https://github.com/iflytek/skillhub/compare/v0.2.16...v0.2.17>
- Compared base commit: `6e133c006e492dc3f468d91b21960aff1d577150`
- Delta: 20 commits; no upstream Flyway migration; schema remains V43.
- Latest released CLI remains
  [`cli-v0.1.9`](https://github.com/iflytek/skillhub/releases/tag/cli-v0.1.9),
  published `2026-07-22T09:47:12Z`; no CLI version bump is in scope.

The release adds immutable `x-astron-compliance` metadata projections,
administrator namespace governance, API-token authorization corrections,
post-commit scan-task delivery, confirm-publish event restoration, and small
developer/Aliyun script fixes.

## Local Baseline Evidence

- The completed local baseline is
  `docs/backend-python-maintenance/results/2026-08-10-v0.2.16-follow-up.md`.
- That result fixes the local baseline at
  `0abff8c87afd901a9f626f23a516204f6e6469cb` and records a fully Python backend,
  released CLI `0.1.9`, Python scanner, real PostgreSQL/Redis verification, and
  root plus `/skillhub` deployment coverage.
- `deploy/k8s/README.md` deploys only web, Python backend, and Python scanner;
  PostgreSQL, Redis, MinIO/S3, and OIDC remain external services.
- `skill_version.parsed_metadata_json` already preserves immutable per-version
  frontmatter. Prefer a validated compliance projection from this snapshot;
  do not add a table or migration unless a failing contract test proves that
  the existing version JSON cannot meet the release contract.
- The current tree already has publish/confirm-publish, security-audit stream,
  social label/star/rating/download, API-token, namespace governance, generated
  OpenAPI, and post-commit side-effect seams. Reuse and deepen those modules.
- Preserve all pre-existing modified and untracked files. This plan file is the
  only repository change made by the release watcher.

## Gap Summary

| Area | Planning-level gap and decision |
| --- | --- |
| Backend Python | Validate `x-astron-compliance` at package ingestion, preserve a normalized immutable version snapshot, expose it in version/detail/search/review responses, add super-admin namespace inspection and governance operations, prove scan tasks publish only after commit, restore the confirm-publish event, and audit token reachability. Port behavior, never Java structure. |
| Schema/migration | Upstream explicitly adds no migration. First use existing `skill_version.parsed_metadata_json`. Add no Python migration unless the approved API/storage contract demonstrably requires new indexed persistence; any such decision needs a separate milestone and real PostgreSQL transaction/index tests. |
| Frontend/API contract | Regenerate OpenAPI types after Python routes/schemas settle. Add compliance panels/cards/review diffs and an admin namespace page using Feature-Sliced Design and TanStack Query. Preserve root and `/skillhub` routing. |
| Scanner | No scanner code or dependency delta. The backend-to-Redis publication boundary changes: verify the existing Python publisher does not expose a stream task before PostgreSQL commit or on rollback. Keep scanner protocol, image pins, retries, and health endpoint unchanged. |
| CLI | No released CLI delta. Keep `0.1.9`; verify new response fields remain additive and existing token-backed label/star/rating/download/auth-method flows do not regress. Do not publish a package. |
| Deployment/K8s | No workload topology or K8s contract change. Compare the `runtime.sh` Aliyun stop URL/flag fix and Makefile Bash launcher fix against local scripts; adapt only if the same commands exist locally. Re-render Compose and Kustomize. |
| Documentation | Document the compliance declaration and runtime-trace boundary, review visibility, admin governance, and any operator-visible script behavior actually adopted. Weekly-site content is a no-op. |
| Tests/verification | Add contract, authorization, transaction/rollback, real PostgreSQL/Redis, frontend, browser, script, and deployment rendering coverage proportional to accepted gaps. |

## Phase 1: Freeze Contracts And Add Failing Tests

1. Re-read the final upstream implementations for PRs `#697`, `#699`, `#703`,
   `#705`, `#707`, `#698`, `#721`, `#729`, `#733`, and `#738` at tag
   `v0.2.17`; record each item as port, already-covered no-op, adapt, or reject.
2. Write the compliance contract before production code:
   - accepted `x-astron-compliance` shape, size/count/string limits, and error
     codes;
   - normalization and immutable version snapshot semantics;
   - absent metadata compatibility;
   - response shapes for version detail, discovery, search suggestions, and
     review comparison;
   - explicit boundary: declarations are publisher claims, not runtime
     execution evidence or proof of compliance.
3. Add failing backend tests for invalid/valid compliance metadata, snapshot
   immutability, publish/review/search projection, and older versions without
   the field.
4. Add failing authorization contract tests that enumerate protected routes
   and prove API tokens can reach every intended label, star, rating, download,
   and `/api/v1/auth/methods` operation while session-only routes remain
   explicitly classified.
5. Add failing transaction tests that prove scan tasks and publish events are
   emitted after commit and never on rollback, including confirm-publish.

Success criteria: the new tests fail only for the identified `v0.2.17` gaps;
the written contract makes optional/absent compliance metadata backward
compatible and does not require a schema migration by assumption.

## Phase 2: Backend Compliance And Search/Review Projection

1. Extend the Python package metadata validator with a small, isolated
   compliance parser/normalizer. Preserve unknown non-reserved frontmatter and
   reject malformed reserved metadata at the publish boundary.
2. Store the normalized declaration inside the immutable
   `parsed_metadata_json` version snapshot. Do not derive current responses
   from a later mutable SKILL.md or skill-level record.
3. Add response schemas and repository/query projections for version detail,
   latest skill detail, portal/search results, suggestions, and review detail.
   Keep SQL in repository/query modules, not routes.
4. Update PostgreSQL search rebuild and incremental refresh so compliance
   framework/control text is searchable without changing visibility rules.
5. Produce a semantic compliance diff for review; compare normalized mappings,
   not JSON serialization order.

Success criteria: focused tests pass; a real PostgreSQL publish creates an
immutable snapshot, search/rebuild returns the same visible mappings, a later
version cannot mutate the earlier projection, and skills without compliance
metadata retain their existing API shapes apart from additive nullable fields.

## Phase 3: Administrator Namespace Governance

1. Compare upstream admin namespace list/detail/stats/permissions and
   governance actions with the current Python namespace/admin modules.
2. Add only missing super-admin routes for listing/inspection, member and role
   management, ownership transfer, freeze, archive, and restore. Compose
   existing namespace workflows rather than duplicating policy or SQL.
3. For every mutation, enforce super-admin authorization, audit actor/reason,
   idempotency where retries are plausible, transaction ownership, lifecycle
   preconditions, and rollback behavior. Preserve the authoritative local
   namespace and skill lifecycle models.
4. Prove a super admin can inspect namespaces without membership, while an
   ordinary non-member cannot gain access.

Success criteria: route/repository tests and real PostgreSQL transaction tests
cover allowed transitions, forbidden transitions, last-owner/ownership
invariants, duplicate requests, rollback, and audit records; existing namespace
member workflows remain compatible.

## Phase 4: Transaction And API-Token Hardening

1. Trace the exact Python publish transaction through security-audit creation
   and Redis `XADD`. If publication can occur before commit, defer it through
   the existing workflow-owned post-commit seam; do not emulate Spring
   transaction callbacks.
2. Prove rollback emits no task. Preserve the existing reclaim/reconciliation
   safety net for old or interrupted tasks rather than deleting it.
3. Trace private confirm-publish through notification/search/subscription or
   other published-skill listeners. Emit the same local domain event once,
   after the status transaction commits, and never on rollback or idempotent
   replay.
4. Align bearer-token access with the documented authorization matrix. Prefer
   an executable route-policy coverage test over two manually synchronized
   allowlists. Explicitly mark cookie/session-only endpoints.

Success criteria: real concurrent PostgreSQL/Redis tests cannot reproduce a
worker observing uncommitted rows; commit publishes exactly once, rollback
publishes zero times, confirm-publish listeners run exactly once after commit,
and session plus bearer matrices pass for labels, stars, ratings, downloads,
and auth-method discovery.

## Phase 5: Frontend And Generated API

1. Regenerate OpenAPI and TypeScript types from the finished Python contract;
   do not hand-edit `web/src/api/generated/`.
2. Add compact compliance mappings to skill detail and discovery cards, plus a
   normalized before/after panel in review detail. Handle absent/large data and
   both English and Chinese locales.
3. Add the super-admin namespace management page using generated types,
   TanStack Query, and existing admin/navigation/access-control patterns.
   Require confirmation and visible error recovery for lifecycle/ownership
   mutations.
4. Preserve React 19 portal isolation, mobile layout, accessibility, lazy-route
   recovery, and root/sub-path navigation.

Success criteria: component tests, typecheck, lint, full frontend tests, and
production build pass; logged-in browser smoke at `/` and `/skillhub` covers
compliance detail/review/search and administrator namespace mutations with no
console errors or horizontal overflow.

## Phase 6: Scripts, Deployment, Documentation, And Final Verification

1. Compare upstream Aliyun `runtime.sh` fixes with the local runtime commands.
   If applicable, use the correct root-level OSS URL and preserve `--aliyun` in
   generated stop commands; add shell contract tests. If no equivalent local
   command exists, record a no-op.
2. Ensure backend developer launchers that contain Bash syntax invoke Bash.
   Keep PowerShell/Windows development commands documented and unchanged.
3. Update compliance protocol/publish/review/runtime-integration docs and admin
   namespace operator docs for behavior actually shipped. Record accepted,
   adapted, rejected, and already-covered release items in a dated result file.
4. Render Compose, Kustomize base/external, and plain manifests. Do not add
   Java, Helm, a new scanner workload, or new infrastructure.

Success criteria: all required checks below pass with exact outputs recorded in
`docs/backend-python-maintenance/results/<dated>-v0.2.17-follow-up.md`.

## Required Verification

Run the narrow tests first, then the full affected suites. Use real PostgreSQL
and Redis for database/stream behavior; mocks are supplementary.

```powershell
cd C:\Users\USER\projects\skillhub\server-python
uv sync --frozen
uv run python -m app.migrations upgrade
uv run pytest tests -q

cd C:\Users\USER\projects\skillhub\web
pnpm run typecheck
pnpm run lint
pnpm test
pnpm run build

cd C:\Users\USER\projects\skillhub
make test-cli
docker build -t skillhub-server-python:v0.2.17-verify -f server-python/Dockerfile .
docker build -t skillhub-web:v0.2.17-verify -f web/Dockerfile web
docker compose --env-file .env.release.example -f compose.release.yml config
kubectl kustomize deploy\k8s\base
kubectl kustomize deploy\k8s\overlays\external
git diff --check
```
Also run focused real-service tests for:

- immutable compliance snapshots, search rebuild, and review diff;
- namespace governance concurrency, rollback, audit, and idempotency;
- scan-task and confirm-publish-event visibility across commit/rollback;
- session-versus-bearer route authorization coverage;
- root and `/skillhub` production-image browser smoke;
- applicable Bash/Aliyun runtime script contracts.

## Documentation To Update During Execution

- `docs/07-skill-protocol.md` or the current local protocol source of truth
- `docs/skillhub/guide/skill-publish.md` and English counterpart
- review and runtime-integration user docs in both supported languages
- administrator namespace/operator documentation
- `deploy/k8s/` only if an operator-visible contract actually changes
- `docs/backend-python-maintenance/results/<dated>-v0.2.17-follow-up.md`

## Explicit Non-Goals

- Do not reintroduce Java, Maven, Spring Boot, Flyway, or a hybrid backend.
- Do not create a schema migration merely because upstream changed Java domain
  classes; upstream `v0.2.17` itself adds no migration.
- Do not treat compliance declarations as verified runtime traces, audit
  evidence, enforcement, or certification.
- Do not replace local namespace/skill lifecycle rules with upstream class
  structure or bypass audit/idempotency/transaction requirements.
- Do not bump or publish the CLI beyond released `0.1.9`.
- Do not change scanner dependencies, protocol, retry policy, or deployment
  topology without an independently demonstrated local gap.
- Do not add Helm or new infrastructure.
- Do not copy the upstream weekly report/site assets.
- Do not broaden into unrelated source-import, collection, governance, cleanup,
  or refactoring work.
- Do not commit, push, deploy, release, or open a PR without later explicit
  authorization.

## Paste-Ready Execution Prompt

```text
Execute docs/backend-python-maintenance/plans/2026-08-21-follow-upstream-v0.2.17.md in C:\Users\USER\projects\skillhub.

Follow AGENTS.md, CLAUDE.md when present, repository skills, and current docs. Use TDD and verify every phase end to end. Treat upstream Java as behavior evidence only: keep the FastAPI/Python backend, Python-owned PostgreSQL migrations, React frontend, released TypeScript CLI 0.1.9, Python scanner, and existing Compose/Kustomize/plain-manifest deployment paths. Preserve all unrelated dirty-worktree files and stage only intended files.

First re-check the official v0.2.17 release/tag and compare its final implementation with the current local tree. Record already-covered items as no-ops. Implement only confirmed gaps: immutable x-astron-compliance validation/projection/search/review behavior, super-admin namespace governance, API-token route parity, post-commit scan task publication, confirm-publish event delivery, generated frontend API and UI, and applicable Aliyun/Bash script fixes. Prefer existing parsed_metadata_json storage because upstream adds no migration; any schema change requires a separately justified milestone and real PostgreSQL evidence. Use real PostgreSQL, Redis, MinIO/scanner, production images, and root plus /skillhub browser verification where relevant. Write the final result under docs/backend-python-maintenance/results/ with exact commands/results. Do not commit, push, deploy, release, or open a PR without explicit authorization.
```
