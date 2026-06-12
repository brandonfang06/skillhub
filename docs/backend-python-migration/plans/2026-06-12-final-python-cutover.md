# Final Python Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion to implement this plan milestone-by-milestone. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Java-to-Python backend migration so SkillHub can run without the Java backend before first production launch.

**Architecture:** Route/proxy ownership has already moved to Python; the remaining work is semantic completion and operational cutover. Complete auth/session/OAuth first because it is the shared security boundary, then globalize route-policy checks, finish active SSE delivery, close deferred lifecycle/governance gaps, transfer database migration ownership, and finally remove Java from local/staging runtime paths.

**Tech Stack:** FastAPI, SQLAlchemy async engine, Redis, pytest, Vitest, Playwright smoke tests, Alembic or equivalent Python migration tooling, existing `scripts/dev-hybrid.ps1` live-gate pattern.

---

## Current Baseline

- `docs/backend-python-migration/route-registry.md` has no `java` owner rows.
- `web/vite.config.ts` has no `http://localhost:8080` proxy target.
- `/api/**` traffic reaches Python by default.
- `/oauth2/authorization/{registrationId}` reaches Python. Complete provider registrations redirect to the provider authorization URI; intentionally incomplete local-dev registrations return `error.auth.oauth.deferred`.

The remaining work is not mainly route ownership. It is the behavior still marked deferred in `docs/backend-python-migration/migration-sequence-plan.md`.

## Milestone 114: Deferred Surface Audit And Cutover Baseline

**Purpose:** Convert the current "still deferred" notes into a machine-checked baseline before changing more code.

**Files:**
- Create: `server-python/tests/test_final_cutover_baseline.py`
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Modify: `docs/backend-python-migration/route-registry.md`
- Create: `docs/backend-python-migration/results/2026-06-12-final-cutover-baseline.md`

**Implementation steps:**
- [x] Add tests that assert route registry has no `| java |` owner rows.
- [x] Add tests that assert Vite config has no Java `8080` proxy targets.
- [x] Add tests that assert final deferred categories are explicitly listed as:
  - OAuth provider redirect/callback/session establishment.
  - Global bearer route-policy enforcement.
  - Active notification SSE fanout.
  - Post-publish lifecycle/governance semantic audit.
  - Python schema migration ownership.
  - Note: the SSE fanout and lifecycle/governance categories above were baseline categories at
    milestone 114 and are closed by milestones 117 and 118.
- [x] Update the migration sequence with this final cutover plan link.
- [x] Verify:
  - `uv run pytest tests/test_final_cutover_baseline.py tests/test_route_registry.py -q`
  - `npm.cmd run test -- vite.config.test.ts`
  - `rg -n "target:\s*'http://localhost:8080'|toBe\('http://localhost:8080'\)" web\vite.config.ts web\vite.config.test.ts`
  - `git diff --name-only -- server`

**Done when:** the remaining gap list is explicit, tested, and no Java route/proxy owner can reappear silently.

## Milestone 115: Python Session And OAuth Completion

**Purpose:** Replace the last Java-auth semantics: real web session establishment and OAuth callback handling.

**Status:** Completed for code-level Python ownership. Milestone 115.1 completed the Python-owned session cookie path and OAuth redirect/callback boundary. Milestone 115.2 added Java-compatible environment provider config, default provider token/userinfo exchange, database identity binding/upsert, and a Redis-compatible session store hook. External-provider live verification requires real OAuth client credentials and is recorded as an operational validation gate rather than a Java dependency.

**Files:**
- Create or modify: `server-python/app/auth/session.py`
- Modify: `server-python/app/api/auth.py`
- Modify: `server-python/app/api/local_auth.py`
- Create or modify: `server-python/app/api/oauth.py` if splitting OAuth out of `auth.py` keeps the file readable.
- Test: `server-python/tests/test_session_auth.py`
- Test: `server-python/tests/test_oauth_flow.py`
- Modify: `web/vite.config.test.ts`
- Create: `docs/backend-python-migration/results/2026-06-12-session-oauth-completion.md`

**Implementation steps:**
- [x] Add failing tests for cookie-backed session creation on migrated local login.
- [x] Add failing tests for `GET /api/v1/auth/me` resolving a session cookie without `X-Mock-User-Id`.
- [x] Add failing tests for session logout or session invalidation if the frontend currently depends on it.
- [x] Add failing tests for `/oauth2/authorization/{registrationId}` returning a provider redirect when OAuth client config is present.
- [ ] Add failing tests for `/login/oauth2/code/{registrationId}` callback behavior:
  - [x] Reject missing `code` or unknown provider.
  - [x] Exchange callback through an injectable OAuth client abstraction.
  - [x] Upsert or link user identity using the existing account merge/identity tables.
  - [x] Create the same Python session cookie used by local login.
  - [x] Redirect to the sanitized remembered `returnTo` value.
- [x] Add a Redis-compatible session store hook while preserving in-process fallback for no-Redis unit tests.
- [x] Implement default OAuth provider config loading from environment/settings.
- [x] Replace `error.auth.oauth.deferred` with working default provider redirect/callback behavior when provider config is complete and no test abstraction is injected.
- [x] Keep deterministic `501 error.auth.oauth.deferred` only when provider config is intentionally incomplete in local dev.
- [x] Verify:
  - `uv run pytest tests/test_session_auth.py tests/test_oauth_flow.py tests/test_oauth_boundary.py tests/test_auth_method_catalog.py -q`
  - `npm.cmd run test -- vite.config.test.ts`
  - Hybrid live gate for local login/session route parity, plus unit-level OAuth configured/deferred/default exchange coverage.

**Done when:** a browser can establish a Python-owned authenticated session without Java, and OAuth no longer depends on Spring Security.

## Milestone 116: Global Principal And Route-Policy Enforcement

**Purpose:** Make every Python-owned protected route use one current-principal and route-policy path instead of route-local bearer/mock handling.

**Status:** Completed for the current Python-owned protected-route surface. Milestone 116.1 completed the shared principal resolver/policy foundation
and removed direct imports of the private `app.api.auth._read_current_user_or_401` helper from the
high-risk admin, token, publish, and hard-delete route modules. Milestone 116.2 moved the remaining
route-module `read_current_mock_user` imports to `app.auth.context` and fixed social delete route
ordering so `DELETE /api/web/skills/{skillId}/star` and subscription routes are not captured by the
broad lifecycle hard-delete route. Milestone 116.3 added shared platform-role helpers and moved route-level role extraction
and simple platform-role guards to `app.auth.policy`. Milestone 116.4 added shared namespace-role
helpers and moved namespace manager/member/owner checks for namespace, lifecycle, promotion,
review, governance, security audit, label, and skill visibility paths to `app.auth.policy`. It also
updated stale lifecycle hybrid gates so rerelease is asserted as Python-owned rather than
Java-owned. Milestone 121, executed after the runtime cutover, removed route-local mock-only principal helpers from account merge,
admin, governance, profile, device auth, report, security audit, labels, notifications, social,
lifecycle, promotion, and review API modules. Those routes now resolve mock/session principals
through `app.auth.context.resolve_current_user_or_401`; unit-test-only mock fallbacks live in the
shared resolver instead of in route modules. It closes the remaining Milestone 116 final-acceptance
gap without changing the completed Milestone 120 runtime-cutover status.

**Files:**
- Modify: `server-python/app/auth/context.py` or create it if no central module exists.
- Modify: `server-python/app/auth/policy.py` or create it if no central module exists.
- Modify: Python route modules that still parse bearer/mock auth locally.
- Test: `server-python/tests/test_route_policy_enforcement.py`
- Test: existing protected-route tests touched by the centralization.
- Create: `docs/backend-python-migration/results/2026-06-12-global-route-policy-cutover.md`

**Implementation steps:**
- [x] Add tests that enumerate protected Python routes and expected principal types.
- [x] Add foundation tests for missing scope `403`, unsupported bearer-on-admin `403`, and non-token principal pass-through.
- [x] Add full route tests for invalid bearer `401`, missing scope `403`, unsupported bearer-on-admin `403`, and mock-user precedence.
- [x] Add session-aware principal resolver behavior after Milestone 115.
- [x] Implement one principal resolver with explicit precedence:
  - local mock user for development gates.
  - bearer API token.
  - session cookie.
- [x] Implement shared policy helpers for required platform roles and bearer scopes.
- [x] Implement shared policy helpers for namespace roles.
- [x] Implement initial policy helpers for API-token bearer scopes and unsupported API-token principals on admin/web-only routes.
- [x] Replace duplicated route-local auth checks in high-risk modules first: admin, publish, lifecycle hard-delete, tokens.
- [x] Move remaining API route module principal-helper imports from `app.api.auth` to `app.auth.context`.
- [x] Replace route-local namespace role predicates in namespace, lifecycle, promotion, review,
  governance, security audit, label, and skill visibility modules with shared namespace-role
  helpers.
- [x] Verify:
  - `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_* tests/test_*token* -q`
  - `uv run pytest tests -q`

**Done when:** route authorization is centralized, tested, and no migrated route relies on ad hoc bearer/session parsing.

## Milestone 117: Active Notification SSE Fanout

**Purpose:** Finish notification SSE beyond connection establishment by delivering real notification events from Python.

**Status:** Completed for the single Python backend runtime path. Python now has an in-process
notification fanout manager, Java-compatible SSE notification payload builder, app-level SSE manager
wiring, and report-submit notification publishing after commit. Multi-process Redis-backed fanout is
left as an operational scaling enhancement if the pre-launch deployment runs more than one Python
backend replica.

**Files:**
- Modify: `server-python/app/api/notifications.py`
- Create or modify: `server-python/app/notifications/fanout.py`
- Create or modify: `server-python/app/notifications/publisher.py`
- Test: `server-python/tests/test_notification_sse_fanout.py`
- Create: `docs/backend-python-migration/results/2026-06-12-notification-sse-fanout.md`

**Implementation steps:**
- [x] Add tests for connected event, heartbeat, and user-scoped notification delivery.
- [x] Add tests proving one user's notification does not fan out to another user's SSE stream.
- [ ] Add tests for reconnect behavior if the current frontend uses last-event-id or polling fallback.
- [x] Implement active fanout for the single Python backend runtime using the same Java SSE event
  shape. Redis-backed fanout remains a scaling enhancement for multi-replica deployment.
- [x] Wire migrated notification-producing workflows to publish fanout events after commit.
- [x] Verify:
  - `uv run pytest tests/test_notification_sse_fanout.py tests/test_notifications.py tests/test_governance.py -q`
  - Hybrid SSE live gate with one connected client and one notification-producing action.

**Done when:** the Python SSE route is not only connectable but also delivers committed notification events.

## Milestone 118: Deferred Lifecycle/Governance Semantic Audit

**Purpose:** Close or remove the broad "post-publish lifecycle/governance deferred" note with evidence.

**Status:** Completed. A route-shape audit now checks representative lifecycle/governance Python
routes against the FastAPI app and route registry. The current registry no longer carries broad
stale Java-owned/deferred lifecycle/governance wording, and the result note records each audited
capability bucket plus the remaining non-Java follow-ups.

**Files:**
- Create: `server-python/tests/test_final_lifecycle_governance_audit.py`
- Modify: route tests for any missing behavior found by the audit.
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Modify: `docs/backend-python-migration/route-registry.md`
- Create: `docs/backend-python-migration/results/2026-06-12-lifecycle-governance-deferred-audit.md`

**Implementation steps:**
- [x] Add a route matrix test that compares `server-python` registered routes against route registry entries.
- [x] Add an audit note for each remaining lifecycle/governance capability:
  - publish side effects.
  - review and promotion transitions.
  - admin hide/unhide/yank/report/profile review actions.
  - skill tag/label/report/social/delete flows.
  - governance summary/inbox/activity/legacy notification behavior.
- [x] For each uncovered gap, either implement the Python behavior with TDD or mark it as intentionally not in product scope before launch.
- [x] Remove stale "Java-owned" wording from old historical sections only when it no longer describes current state.
- [x] Verify:
  - `uv run pytest tests/test_final_lifecycle_governance_audit.py tests/test_route_registry.py -q`
  - Existing affected route tests.
  - One hybrid live gate covering representative lifecycle/governance side effects.

**Done when:** no broad lifecycle/governance deferred bucket remains without a concrete route, test, or explicit product-scope decision.

## Milestone 119: Python Schema Migration Takeover

**Purpose:** Move database schema ownership from Java Flyway to Python before Java backend deprecation.

**Status:** Completed. Python now has an Alembic baseline marker plus a migration command that can
initialize a fresh database from the existing Flyway SQL baseline or stamp an existing Flyway-created
schema without replaying legacy SQL. Java Flyway files remain read-only reference material.

**Files:**
- Create: `server-python/alembic.ini`
- Create: `server-python/alembic/env.py`
- Create: `server-python/alembic/versions/<baseline>_baseline_existing_flyway_schema.py`
- Modify: local DB setup scripts that currently rely on Java Flyway.
- Modify: CI/staging scripts that initialize or validate schema.
- Test: `server-python/tests/test_schema_migration_baseline.py`
- Create: `docs/backend-python-migration/results/2026-06-12-python-schema-migration-takeover.md`

**Implementation steps:**
- [x] Add a test that verifies Python migration metadata can stamp an existing Flyway-created schema.
- [x] Add a test that verifies a fresh database can be initialized by the Python migration command.
- [x] Add Alembic baseline without trying to recreate already-applied Flyway migrations.
- [x] Wire Python migration command into local dependency startup.
- [x] Wire Python migration command into staging/CI validation.
- [x] Keep Java Flyway files in `server/` read-only until the final Java deprecation milestone, then remove references only after the Python migration path is verified.
- [x] Verify:
  - `uv run pytest tests/test_schema_migration_baseline.py -q`
  - Fresh local DB bootstrap.
  - Existing DB stamp/upgrade path.
  - Staging schema validation.

**Done when:** Python owns schema initialization/upgrade for both fresh and existing databases.

## Milestone 120: Java Runtime Deprecation And Staging Cutover

**Purpose:** Make the default local/staging runtime start Python without Java.

**Status:** Completed. Default `make dev-all`, `make dev-server`, and `make staging` now use the
Python backend. Java backend commands remain available only through explicit reference/hybrid
workflows, not the default local or staging path.

**Files:**
- Modify: `scripts/dev-hybrid.ps1` or add a new Python-only dev script.
- Modify: Docker Compose and staging scripts that still build/start the Java backend.
- Modify: `scripts/smoke-test.sh` if smoke gates still target Java actuator endpoints.
- Modify: docs that describe backend runtime ports and startup commands.
- Test: `server-python/tests/test_final_cutover_baseline.py`
- Test: `server-python/tests/test_python_runtime_cutover.py`
- Test: `server-python/tests/test_bootstrap_admin.py`
- Test: `server-python/tests/test_health.py`
- Test: frontend smoke/E2E configs as needed.
- Create: `docs/backend-python-migration/results/2026-06-12-java-runtime-deprecation.md`

**Implementation steps:**
- [x] Add tests or script checks that fail if default dev/staging paths require Java for HTTP traffic.
- [x] Keep a clearly named Java reference script only for historical parity checks, not default development.
- [x] Update local startup to run dependencies, Python backend, scanner, and frontend.
- [x] Update staging to build/deploy Python backend as the service backend.
- [x] Update staging smoke checks to use Python health and metrics endpoints.
- [x] Add Python bootstrap admin seeding for staging admin smoke parity.
- [x] Update docs to mark Java backend as deprecated/reference-only.
- [x] Verify:
  - Python-only local stack starts.
  - `http://localhost:3000/api/v1/health` reaches Python.
  - frontend smoke passes against Python-only stack.
  - staging passes without Java backend.
  - `git diff --name-only -- server` is empty unless the final deprecation step is explicitly allowed to remove Java runtime references.

**Done when:** SkillHub can be started, tested, and staged without the Java backend.

## Execution Order

1. Milestone 114: Deferred surface audit and cutover baseline.
2. Milestone 115: Python session and OAuth completion.
3. Milestone 116: Global principal and route-policy enforcement.
4. Milestone 117: Active notification SSE fanout.
5. Milestone 118: Deferred lifecycle/governance semantic audit.
6. Milestone 119: Python schema migration takeover.
7. Milestone 120: Java runtime deprecation and staging cutover.

## Final Acceptance Gate

Before declaring the Java-to-Python migration complete:

- [ ] `docs/backend-python-migration/route-registry.md` has no `java` owner rows.
- [ ] Vite config has no Java `8080` target.
- [x] Python sessions and OAuth work without Java.
- [x] Global route-policy enforcement outside the completed high-risk foundation slice is complete.
- [x] SSE delivers active notifications.
- [x] No broad deferred lifecycle/governance bucket remains.
- [x] Python schema migrations initialize fresh DBs and stamp/upgrade existing DBs.
- [x] Java runtime deprecation from default local/staging paths is complete.
- [ ] All result docs are written.
- [ ] Final regression and smoke gates pass.
