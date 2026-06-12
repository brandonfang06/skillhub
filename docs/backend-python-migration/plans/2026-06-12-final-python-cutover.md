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

**Status:** In progress. Milestone 116.1 completed the shared principal resolver/policy foundation
and removed direct imports of the private `app.api.auth._read_current_user_or_401` helper from the
high-risk admin, token, publish, and hard-delete route modules. Remaining work is broader protected
route enumeration plus role/namespace policy coverage for governance, reports, and the rest of the
authenticated route surface.

**Files:**
- Modify: `server-python/app/auth/context.py` or create it if no central module exists.
- Modify: `server-python/app/auth/policy.py` or create it if no central module exists.
- Modify: Python route modules that still parse bearer/mock auth locally.
- Test: `server-python/tests/test_route_policy_enforcement.py`
- Test: existing protected-route tests touched by the centralization.
- Create: `docs/backend-python-migration/results/2026-06-12-global-route-policy-cutover.md`

**Implementation steps:**
- [ ] Add tests that enumerate protected Python routes and expected principal types.
- [x] Add foundation tests for missing scope `403`, unsupported bearer-on-admin `403`, and non-token principal pass-through.
- [ ] Add full route tests for invalid bearer `401`, missing scope `403`, unsupported bearer-on-admin `403`, and mock-user precedence.
- [x] Add session-aware principal resolver behavior after Milestone 115.
- [x] Implement one principal resolver with explicit precedence:
  - local mock user for development gates.
  - bearer API token.
  - session cookie.
- [ ] Implement one policy helper for required platform roles, namespace roles, and bearer scopes.
- [x] Implement initial policy helpers for API-token bearer scopes and unsupported API-token principals on admin/web-only routes.
- [x] Replace duplicated route-local auth checks in high-risk modules first: admin, publish, lifecycle hard-delete, tokens.
- [ ] Replace remaining route-local auth checks in governance, reports, and other authenticated route modules.
- [ ] Verify:
  - `uv run pytest tests/test_route_policy_enforcement.py tests/test_admin_* tests/test_*token* -q`
  - Hybrid live gate comparing representative protected route outcomes across Python direct and Vite.

**Done when:** route authorization is centralized, tested, and no migrated route relies on ad hoc bearer/session parsing.

## Milestone 117: Active Notification SSE Fanout

**Purpose:** Finish notification SSE beyond connection establishment by delivering real notification events from Python.

**Files:**
- Modify: `server-python/app/api/notifications.py`
- Create or modify: `server-python/app/notifications/fanout.py`
- Create or modify: `server-python/app/notifications/publisher.py`
- Test: `server-python/tests/test_notification_sse_fanout.py`
- Create: `docs/backend-python-migration/results/2026-06-12-notification-sse-fanout.md`

**Implementation steps:**
- [ ] Add tests for connected event, heartbeat, and user-scoped notification delivery.
- [ ] Add tests proving one user's notification does not fan out to another user's SSE stream.
- [ ] Add tests for reconnect behavior if the current frontend uses last-event-id or polling fallback.
- [ ] Implement Redis pub/sub or stream-backed fanout using the existing Redis dependency.
- [ ] Wire migrated notification-producing workflows to publish fanout events after commit.
- [ ] Verify:
  - `uv run pytest tests/test_notification_sse_fanout.py tests/test_notifications.py tests/test_governance.py -q`
  - Hybrid SSE live gate with one connected client and one notification-producing action.

**Done when:** the Python SSE route is not only connectable but also delivers committed notification events.

## Milestone 118: Deferred Lifecycle/Governance Semantic Audit

**Purpose:** Close or remove the broad "post-publish lifecycle/governance deferred" note with evidence.

**Files:**
- Create: `server-python/tests/test_final_lifecycle_governance_audit.py`
- Modify: route tests for any missing behavior found by the audit.
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
- Modify: `docs/backend-python-migration/route-registry.md`
- Create: `docs/backend-python-migration/results/2026-06-12-lifecycle-governance-deferred-audit.md`

**Implementation steps:**
- [ ] Add a route matrix test that compares `server-python` registered routes against route registry entries.
- [ ] Add an audit note for each remaining lifecycle/governance capability:
  - publish side effects.
  - review and promotion transitions.
  - admin hide/unhide/yank/report/profile review actions.
  - skill tag/label/report/social/delete flows.
  - governance summary/inbox/activity/legacy notification behavior.
- [ ] For each uncovered gap, either implement the Python behavior with TDD or mark it as intentionally not in product scope before launch.
- [ ] Remove stale "Java-owned" wording from old historical sections only when it no longer describes current state.
- [ ] Verify:
  - `uv run pytest tests/test_final_lifecycle_governance_audit.py tests/test_route_registry.py -q`
  - Existing affected route tests.
  - One hybrid live gate covering representative lifecycle/governance side effects.

**Done when:** no broad lifecycle/governance deferred bucket remains without a concrete route, test, or explicit product-scope decision.

## Milestone 119: Python Schema Migration Takeover

**Purpose:** Move database schema ownership from Java Flyway to Python before Java backend deprecation.

**Files:**
- Create: `server-python/alembic.ini`
- Create: `server-python/alembic/env.py`
- Create: `server-python/alembic/versions/<baseline>_baseline_existing_flyway_schema.py`
- Modify: local DB setup scripts that currently rely on Java Flyway.
- Modify: CI/staging scripts that initialize or validate schema.
- Test: `server-python/tests/test_schema_migration_baseline.py`
- Create: `docs/backend-python-migration/results/2026-06-12-python-schema-migration-takeover.md`

**Implementation steps:**
- [ ] Add a test that verifies Python migration metadata can stamp an existing Flyway-created schema.
- [ ] Add a test that verifies a fresh database can be initialized by the Python migration command.
- [ ] Add Alembic baseline without trying to recreate already-applied Flyway migrations.
- [ ] Wire Python migration command into local dependency startup.
- [ ] Wire Python migration command into staging/CI validation.
- [ ] Keep Java Flyway files in `server/` read-only until the final Java deprecation milestone, then remove references only after the Python migration path is verified.
- [ ] Verify:
  - `uv run pytest tests/test_schema_migration_baseline.py -q`
  - Fresh local DB bootstrap.
  - Existing DB stamp/upgrade path.
  - Staging schema validation.

**Done when:** Python owns schema initialization/upgrade for both fresh and existing databases.

## Milestone 120: Java Runtime Deprecation And Staging Cutover

**Purpose:** Make the default local/staging runtime start Python without Java.

**Files:**
- Modify: `scripts/dev-hybrid.ps1` or add a new Python-only dev script.
- Modify: Docker Compose and staging scripts that still build/start the Java backend.
- Modify: docs that describe backend runtime ports and startup commands.
- Test: `server-python/tests/test_final_cutover_baseline.py`
- Test: frontend smoke/E2E configs as needed.
- Create: `docs/backend-python-migration/results/2026-06-12-java-runtime-deprecation.md`

**Implementation steps:**
- [ ] Add tests or script checks that fail if default dev/staging paths require Java for HTTP traffic.
- [ ] Keep a clearly named Java reference script only for historical parity checks, not default development.
- [ ] Update local startup to run dependencies, Python backend, scanner, and frontend.
- [ ] Update staging to build/deploy Python backend as the service backend.
- [ ] Update docs to mark Java backend as deprecated/reference-only.
- [ ] Verify:
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
- [ ] Protected routes use the centralized principal/policy path.
- [ ] SSE delivers active notifications.
- [ ] No broad deferred lifecycle/governance bucket remains.
- [ ] Python schema migrations initialize fresh DBs and stamp/upgrade existing DBs.
- [ ] Default local/staging runtime does not start or require Java.
- [ ] All result docs are written.
- [ ] Final regression and smoke gates pass.
