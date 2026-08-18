# Service Principal Source Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace human API-token authentication for OSS source imports with independently managed service principals and expiring service tokens while preserving human attribution, scanner review, and all existing user-token behavior.

**Architecture:** Add isolated `service_principal` and `service_token` tables and a dedicated bearer resolver used only by source-import routes. Platform Admin management lives behind session-authenticated SUPER_ADMIN APIs and a React admin page. Source-import transactions retain user foreign keys for the resolved human while recording the service actor separately in provenance and audit.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async with explicit SQL, PostgreSQL 16, React 19, TypeScript, TanStack Query, Vitest, Playwright, Docker Compose, Redis, MinIO, Python scanner.

---

## File Structure

- `server-python/app/db/local_migration/20260818_02__service_principal_auth.sql` — additive service principal, service token, audit actor, and OSS provenance schema.
- `server-python/app/service_accounts/contracts.py` — immutable service-principal/token/auth DTOs and validation types.
- `server-python/app/service_accounts/repository.py` — all service-account SQL reads and writes.
- `server-python/app/service_accounts/service.py` — admin lifecycle, validation, token generation, rotation, and audit workflows.
- `server-python/app/auth/service_tokens.py` — dedicated `st_` bearer parsing and authentication.
- `server-python/app/api/admin_service_principals.py` — transport-only SUPER_ADMIN management routes.
- `server-python/app/api/source_imports.py` — source import now resolves a service actor instead of a user bearer principal.
- `server-python/app/source_import/service.py` and `repository.py` — preserve human attribution and persist service actor separately.
- `server-python/app/audit/writer.py` and `app/admin/audit_repository.py` — discriminated user/service audit actors without changing existing user writes.
- `web/src/features/admin/service-principals.ts` — generated-type-backed query/mutation hooks.
- `web/src/pages/admin/service-principals.tsx` — Platform Admin service-account lifecycle UI and one-time token dialog.
- `tools/oss-source-importer/` — require `SKILLHUB_SERVICE_TOKEN` and report service identity.
- `scripts/oss-source-import-smoke-test.ps1` — provision through admin API and verify service/user identity separation end to end.

## Task 1: Add the additive PostgreSQL contract

**Files:**

- Create: `server-python/app/db/local_migration/20260818_02__service_principal_auth.sql`
- Modify: `server-python/app/db/models.py`
- Modify: `server-python/tests/test_schema_migration_baseline.py`
- Create: `server-python/tests/test_service_principal_schema_postgres.py`
- Modify: `server-python/tests/test_orm_mapping.py`

- [ ] Write failing schema tests asserting `service_principal`, `service_token`, `audit_log.actor_service_principal_id`, and the three OSS service-actor foreign keys exist. Assert the active-token name index is partial and case-insensitive.
- [ ] Run:

  ```powershell
  cd server-python
  $env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_smoke_db@127.0.0.1:55432/skillhub'
  uv run --no-cache pytest tests/test_schema_migration_baseline.py tests/test_service_principal_schema_postgres.py tests/test_orm_mapping.py -q
  ```

  Expected: failures naming the missing migration/tables/columns.

- [ ] Add an idempotent migration with this contract:

  ```sql
  CREATE TABLE IF NOT EXISTS service_principal (
      id VARCHAR(128) PRIMARY KEY,
      code VARCHAR(100) NOT NULL UNIQUE,
      display_name VARCHAR(200) NOT NULL,
      status VARCHAR(16) NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
      created_by_user_id VARCHAR(128) NOT NULL REFERENCES user_account(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS service_token (
      id BIGSERIAL PRIMARY KEY,
      service_principal_id VARCHAR(128) NOT NULL REFERENCES service_principal(id),
      name VARCHAR(100) NOT NULL,
      token_prefix VARCHAR(16) NOT NULL,
      token_hash CHAR(64) NOT NULL UNIQUE,
      scope_json JSONB NOT NULL,
      created_by_user_id VARCHAR(128) NOT NULL REFERENCES user_account(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      expires_at TIMESTAMPTZ NOT NULL,
      last_used_at TIMESTAMPTZ,
      revoked_at TIMESTAMPTZ
  );

  CREATE UNIQUE INDEX IF NOT EXISTS uk_service_token_active_name
      ON service_token (service_principal_id, LOWER(name))
      WHERE revoked_at IS NULL;
  ```

  Add indexes for hash/principal/expiry, nullable audit and provenance service-principal foreign keys, and preserve every existing row with null new columns.

- [ ] Map only the new `AuditLog.actor_service_principal_id` column in the existing ORM model; keep service-account persistence behind explicit SQL.
- [ ] Run the focused schema tests until they pass and run `uv run python -m app.migrations upgrade` against the real PostgreSQL service.
- [ ] Commit:

  ```powershell
  git add server-python/app/db server-python/tests/test_schema_migration_baseline.py server-python/tests/test_service_principal_schema_postgres.py server-python/tests/test_orm_mapping.py
  git commit -m "feat(auth): add service principal schema"
  ```

## Task 2: Implement service-principal lifecycle and token security

**Files:**

- Create: `server-python/app/service_accounts/__init__.py`
- Create: `server-python/app/service_accounts/contracts.py`
- Create: `server-python/app/service_accounts/repository.py`
- Create: `server-python/app/service_accounts/service.py`
- Create: `server-python/tests/test_service_accounts.py`
- Create: `server-python/tests/test_service_accounts_postgres.py`

- [ ] Write failing unit tests for immutable lowercase code validation, nonblank display/token names, exact scope allowlist `{"source:import"}`, `st_` generation, required future expiry no later than 365 days, disabled-principal denial, one-time raw token response, revoke idempotency, and rotation rollback.
- [ ] Define focused contracts, including:

  ```python
  @dataclass(frozen=True)
  class ServicePrincipal:
      id: str
      code: str
      display_name: str
      status: Literal["ACTIVE", "DISABLED"]

  @dataclass(frozen=True)
  class ServiceTokenSecret:
      id: int
      service_principal_id: str
      name: str
      token_prefix: str
      token: str
      scopes: tuple[str, ...]
      expires_at: datetime
  ```

- [ ] Implement repository methods for paginated list, create, rename/status update, token list/create/revoke/rotate, active-name lookup, and transactional audit writes. Generate principal ids as `svc_` plus UUID hex and raw tokens as `st_` plus `secrets.token_urlsafe(32)`; persist only SHA-256.
- [ ] Make rotation one transaction: insert replacement with a temporary non-conflicting name or revoke then insert under the same active-name constraint, with any failure rolling back both operations. Return the raw replacement only after commit succeeds.
- [ ] Write PostgreSQL integration tests proving concurrent uniqueness, last-active-name behavior after revoke, disable/enable preservation, and rollback on invalid rotation.
- [ ] Run:

  ```powershell
  uv run --no-cache pytest tests/test_service_accounts.py tests/test_service_accounts_postgres.py -q
  ```

  Expected: all tests pass with PostgreSQL integration enabled.

- [ ] Commit:

  ```powershell
  git add server-python/app/service_accounts server-python/tests/test_service_accounts*.py
  git commit -m "feat(auth): manage service principal tokens"
  ```

## Task 3: Add the dedicated service-token resolver

**Files:**

- Create: `server-python/app/auth/service_tokens.py`
- Create: `server-python/tests/test_auth_service_tokens.py`
- Modify: `server-python/tests/test_auth_bearer.py`
- Modify: `server-python/tests/test_route_policy_enforcement.py`

- [ ] Write failing tests for valid service resolution, invalid prefix/hash, expired/revoked token, disabled principal, missing scope, last-used update, and safe errors that never contain raw token text.
- [ ] Implement a dedicated result type:

  ```python
  @dataclass(frozen=True)
  class ServiceTokenPrincipal:
      service_principal_id: str
      code: str
      display_name: str
      token_id: int
      token_scopes: tuple[str, ...]
  ```

  `resolve_service_token_or_401()` must accept only `st_`, query only the service tables, update `last_used_at`, and never call `build_auth_me_response()`.

- [ ] Keep `read_current_bearer_user()` and `api_token` SQL byte-for-byte behaviorally compatible. Add regression tests proving `sk_` user tokens still work and `st_` never resolves as a user.
- [ ] Run:

  ```powershell
  uv run --no-cache pytest tests/test_auth_service_tokens.py tests/test_auth_bearer.py tests/test_route_policy_enforcement.py -q
  ```

- [ ] Commit:

  ```powershell
  git add server-python/app/auth/service_tokens.py server-python/tests/test_auth_service_tokens.py server-python/tests/test_auth_bearer.py server-python/tests/test_route_policy_enforcement.py
  git commit -m "feat(auth): resolve isolated service tokens"
  ```

## Task 4: Expose SUPER_ADMIN service-account management APIs

**Files:**

- Create: `server-python/app/api/admin_service_principals.py`
- Modify: `server-python/app/main.py`
- Create: `server-python/tests/test_admin_service_principals_api.py`
- Create: `server-python/tests/test_admin_service_principals_postgres.py`

- [ ] Write route tests for unauthenticated, non-SUPER_ADMIN, user bearer, service bearer, valid SUPER_ADMIN, response envelope/request id, 400 validation, 404, 409, one-time secret, and idempotent 204 revoke.
- [ ] Add Pydantic request/response models for the seven routes in the design. Reuse `reject_bearer_api_token_for_admin_route()` first, then require `SUPER_ADMIN`; do not put SQL in the route.
- [ ] Add real transaction tests that create through the route/workflow, list metadata without raw token, rotate and prove the old hash is revoked, disable and re-enable, and inspect user-actor audit entries.
- [ ] Register the router in `app/main.py` and run:

  ```powershell
  uv run --no-cache pytest tests/test_admin_service_principals_api.py tests/test_admin_service_principals_postgres.py -q
  ```

- [ ] Commit:

  ```powershell
  git add server-python/app/api/admin_service_principals.py server-python/app/main.py server-python/tests/test_admin_service_principals*.py
  git commit -m "feat(admin): expose service account management"
  ```

## Task 5: Make audit actors explicitly user or service

**Files:**

- Modify: `server-python/app/audit/writer.py`
- Modify: `server-python/app/admin/audit_repository.py`
- Modify: `server-python/app/api/admin_audit_logs.py`
- Modify: `server-python/tests/test_admin_audit_logs.py`
- Modify: `server-python/tests/test_audit_writer.py`

- [ ] Write failing tests that existing user writes still populate only `actor_user_id`, service writes populate only `actor_service_principal_id`, invalid dual actors fail before SQL, and admin audit results return `actorType`, `actorId`, and `actorName` for both variants.
- [ ] Change `write_audit_log()` to accept exactly one of `actor_user_id` or `actor_service_principal_id`, while keeping existing call sites source-compatible through keyword defaults.
- [ ] Extend the admin audit query with a left join to `service_principal` and project:

  ```json
  {
    "actorType": "SERVICE",
    "actorId": "svc_...",
    "actorName": "GitLab OSS Importer"
  }
  ```

  Keep legacy `userId` and `username` fields for user audit consumers.

- [ ] Run audit and existing admin bearer-policy tests, then commit:

  ```powershell
  git add server-python/app/audit server-python/app/admin/audit_repository.py server-python/app/api/admin_audit_logs.py server-python/tests/test_admin_audit_logs.py server-python/tests/test_audit_writer.py
  git commit -m "feat(audit): distinguish service actors"
  ```

## Task 6: Cut source-import authorization over to service actors

**Files:**

- Modify: `server-python/app/api/source_imports.py`
- Modify: `server-python/app/source_import/contracts.py`
- Modify: `server-python/app/source_import/service.py`
- Modify: `server-python/app/source_import/repository.py`
- Modify: `server-python/app/publish/orchestration.py`
- Modify: `server-python/app/publish/side_effects.py`
- Modify: `server-python/app/review/archive.py`
- Modify: `server-python/tests/test_source_import_api.py`
- Modify: `server-python/tests/test_source_import_namespace.py`
- Modify: `server-python/tests/test_source_import_submission.py`
- Modify: `server-python/tests/test_source_import_*_postgres.py`
- Modify: `server-python/tests/test_publish_orchestration.py`
- Modify: `server-python/tests/test_publish_side_effects.py`

- [ ] Replace test principals first: valid service token accepted; valid `sk_` user token rejected with 403 `error.sourceImport.serviceToken.required`; disabled/missing-scope service denied before workflow mocks are called.
- [ ] Introduce `SourceServiceActor(service_principal_id, code, display_name)` and replace every source-import `actor_user_id` input with `service_actor`. Keep `stable_owner`, `review_submitter`, namespace owner, membership, `created_by`, and `imported_by` as user ids.
- [ ] Extend `PublishWriteInput`/side effects with nullable `actor_service_principal_id`. When present, do not fall back to the publisher as audit actor. Preserve all existing user publish defaults when absent.
- [ ] Persist source service ids in the new provenance columns and write `SOURCE_IMPORT_NAMESPACE` and `SOURCE_IMPORT_SKILL_VERSION` with service audit actor plus detail fields `initiator*`, `attributedUserId`, and `attributionSource`.
- [ ] Prove with PostgreSQL tests that service ids never enter `namespace_member`, `skill.owner_id`, skill/version `created_by`, or `review_task.submitted_by`; also prove later triggers preserve stable owner.
- [ ] Run all source-import, publish, review-archive, and audit tests, then commit:

  ```powershell
  git add server-python/app/api/source_imports.py server-python/app/source_import server-python/app/publish server-python/app/review/archive.py server-python/tests
  git commit -m "refactor(import): separate service and human actors"
  ```

## Task 7: Regenerate and verify the API contract

**Files:**

- Modify: `web/src/api/generated/schema.d.ts`
- Modify: `web/src/api/generated/source-import-openapi.json`
- Modify: `web/src/api/generated/source-import-schema.d.ts`
- Modify: `server-python/scripts/export_source_import_openapi.py`
- Modify: `server-python/tests/test_source_import_openapi.py`
- Create: `server-python/tests/test_service_principal_openapi.py`

- [ ] Write contract tests for all admin service routes, one-time secret response, audit actor fields, and service actor in source-import responses.
- [ ] Generate the main schema using the repo generator and the focused source-import schema using `server-python/scripts/export_source_import_openapi.py`; never hand-edit generated files.
- [ ] Run OpenAPI drift tests and frontend typecheck, then commit:

  ```powershell
  git add server-python/scripts server-python/tests/test_*openapi.py web/src/api/generated
  git commit -m "chore(api): generate service account contracts"
  ```

## Task 8: Build the Platform Admin Service Accounts UI

**Files:**

- Create: `web/src/features/admin/service-principals.ts`
- Create: `web/src/features/admin/service-principals.test.tsx`
- Create: `web/src/pages/admin/service-principals.tsx`
- Create: `web/src/pages/admin/service-principals.test.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/router.test.ts`
- Modify: `web/src/shared/components/user-menu.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/i18n/locales/zh-TW.json`

- [ ] Write failing hook/component tests for list/create, SUPER_ADMIN menu visibility, status toggle, token metadata, create/rotate/revoke, expiry validation, one-time secret copy/discard, and no raw token in query cache/local storage.
- [ ] Implement TanStack Query hooks using generated types and existing `fetchJson`/query-key conventions. Invalidate only service-principal queries after mutations.
- [ ] Implement `/admin/service-principals` with accessible dialogs and confirmation. Keep the raw token only in component state and clear it when the one-time dialog closes.
- [ ] Add all user-visible strings to three locales and register the lazy route/menu item for SUPER_ADMIN only.
- [ ] Run focused Vitest, typecheck, and lint; commit:

  ```powershell
  git add web/src/features/admin/service-principals* web/src/pages/admin/service-principals* web/src/app web/src/shared/components/user-menu.tsx web/src/i18n
  git commit -m "feat(admin): manage service accounts in UI"
  ```

## Task 9: Require the service token in the Python importer

**Files:**

- Modify: `tools/oss-source-importer/src/skillhub_oss_importer/config.py`
- Modify: `tools/oss-source-importer/src/skillhub_oss_importer/client.py`
- Modify: `tools/oss-source-importer/src/skillhub_oss_importer/orchestrator.py`
- Modify: `tools/oss-source-importer/tests/test_config.py`
- Modify: `tools/oss-source-importer/tests/test_client.py`
- Modify: `tools/oss-source-importer/tests/test_orchestrator.py`
- Modify: `deploy/gitlab/oss-source-import.yml`
- Modify: `tools/oss-source-importer/tests/test_gitlab_template.py`

- [ ] Write failing tests that `SKILLHUB_SERVICE_TOKEN` is required, `SKILLHUB_API_TOKEN` alone fails, the Bearer header uses the service token, and reports expose service actor without confusing it with stable owner/review submitter.
- [ ] Rename the config field to `service_token`; preserve HTTP Bearer transport and stable exit classes. Do not accept a compatibility fallback from the old variable.
- [ ] Change the GitLab template's required variable and comments, run all importer tests/Ruff/build, build the non-root image, and commit:

  ```powershell
  git add tools/oss-source-importer deploy/gitlab/oss-source-import.yml
  git commit -m "feat(importer): require SkillHub service token"
  ```

## Task 10: Update operator documentation

**Files:**

- Modify: `deploy/k8s/oss-github-source-import.zh.md`
- Modify: `deploy/k8s/environment-variables.zh.md`
- Modify: `deploy/k8s/README.md`
- Modify: `README_zh.md`
- Modify: `server-python/tests/test_oss_source_import_docs.py`

- [ ] Write failing documentation contract tests requiring `SKILLHUB_SERVICE_TOKEN`, `st_`, the admin route/page, expiry/rotation/revoke instructions, trigger preferred username, fallback behavior, migration order, and explicit rejection of personal tokens.
- [ ] Rewrite the Chinese SOP with copy-ready GitLab variables and a Platform Admin procedure. Remove instructions to create an ordinary user/service-account API token.
- [ ] Run docs tests and search the active importer/SOP/template for stale `SKILLHUB_API_TOKEN` references; historical design/verification records may retain it as history.
- [ ] Commit:

  ```powershell
  git add deploy/k8s README_zh.md server-python/tests/test_oss_source_import_docs.py
  git commit -m "docs(import): document service token operations"
  ```

## Task 11: Extend full-stack and subpath verification

**Files:**

- Modify: `scripts/oss-source-import-smoke-test.ps1`
- Modify: `web/e2e/subpath-deployment.spec.ts`
- Create: `web/e2e/service-principals.spec.ts`
- Modify: `docker-compose.oss-source-import-test.yml` only if the test contract needs an additive setting.
- Modify: `docs/backend-python-maintenance/oss-source-import-verification.md`

- [ ] Change the smoke to log in as bootstrap SUPER_ADMIN and create a unique service principal/token through the public root Nginx admin API. Do not insert the service credential directly with SQL.
- [ ] Import with that token and assert PostgreSQL rows show the service actor, human trigger, stable owner, review submitter, provenance, scanner audit, and no service id in a user FK.
- [ ] Create an ordinary scoped user token and prove source import returns 403. Rotate through the admin API, prove the old token returns 401, then import one changed skill through `/skillhub` with the replacement.
- [ ] Add Playwright coverage for create, one-time secret, rotate/revoke, disabled principal, desktop/mobile layout, and base-path-safe API calls.
- [ ] Run the full smoke against PostgreSQL, Redis, MinIO, scanner, backend, root web, and subpath web. Record run id, commits, request ids, image digests, exact outcomes, and clean log window in the verification document.
- [ ] Commit:

  ```powershell
  git add scripts/oss-source-import-smoke-test.ps1 web/e2e docker-compose.oss-source-import-test.yml docs/backend-python-maintenance/oss-source-import-verification.md
  git commit -m "test(import): verify service-token source flow"
  ```

## Task 12: Release-quality verification and branch review

**Files:**

- Modify only files required to fix verified failures.

- [ ] Run the complete backend against real PostgreSQL:

  ```powershell
  cd server-python
  $env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_smoke_db@127.0.0.1:55432/skillhub'
  uv sync --frozen
  uv run --no-cache pytest tests -q
  ```

- [ ] Run importer release checks:

  ```powershell
  cd ..\tools\oss-source-importer
  uv sync --frozen
  uv run --no-cache pytest -q
  uv run --no-cache ruff check .
  uv build
  ```

- [ ] Run frontend release checks:

  ```powershell
  cd ..\..\web
  pnpm install --frozen-lockfile
  pnpm run typecheck
  pnpm run lint
  pnpm test -- --run
  pnpm run build
  pnpm exec playwright test e2e/service-principals.spec.ts e2e/subpath-deployment.spec.ts
  ```

- [ ] Run deployment gates and the final full-stack smoke:

  ```powershell
  cd ..
  docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
  docker build -t skillhub-oss-source-importer:verify -f tools/oss-source-importer/Dockerfile tools/oss-source-importer
  kubectl kustomize deploy\k8s\base | Out-Null
  docker compose --env-file .env.release.example -f compose.release.yml config | Out-Null
  docker compose --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml config | Out-Null
  powershell -ExecutionPolicy Bypass -File scripts/oss-source-import-smoke-test.ps1
  git diff --check origin/dev...HEAD
  ```

- [ ] Review the complete branch against the approved design. Confirm there is no Java/Maven/Spring runtime, generic service-token access, user-token regression, service principal in user foreign keys, auto-publish, source fetcher, unrelated cleanup, plaintext token persistence/logging, or dependency on caller shell variables.
- [ ] End with a clean feature worktree and retain the isolated full stack for user acceptance. Do not merge or push without explicit later authorization.

## Acceptance Checklist

- [ ] A Platform Admin can create an ACTIVE service principal and receive an `st_` token exactly once.
- [ ] Token identity and lifetime are independent from the creating admin.
- [ ] Disable, expiry, revoke, and rotation take effect immediately and transactionally.
- [ ] Existing `sk_` tokens and all existing CLI/token/device flows remain compatible.
- [ ] Source import accepts only `st_` with `source:import` and other APIs reject it.
- [ ] GitLab supplies preferred username independently; no triggering user token is needed.
- [ ] New owner, stable owner, review submitter, service actor, and token creator are distinguishable.
- [ ] Missing initiator falls back to current namespace owner; inactive/ambiguous identity fails closed.
- [ ] No service id is written to a user foreign key.
- [ ] Scanner and namespace-owner review remain mandatory; no version auto-publishes.
- [ ] Admin UI never retains raw token after the one-time dialog closes.
- [ ] Root and `/skillhub` routes work with the same service-token contract.
- [ ] PostgreSQL, Redis, MinIO, scanner, backend, and both proxies are healthy during final verification.
- [ ] Chinese SOP documents provisioning, variables, rotation, revocation, review, and troubleshooting.
