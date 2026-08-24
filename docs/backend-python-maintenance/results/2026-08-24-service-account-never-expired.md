# Service Account Never-Expired Token Result

Date: 2026-08-24

Status: implemented and verified; awaiting review before commit

Branch: `codex/service-account-never-expired`

Baseline: `2edbda1cfce505f3de824290752e033be18a1195`

## Root cause of the untranslated buttons

The earlier Service Accounts polish was implemented as seven commits ending at
`8a30082b` on `codex/service-account-ui-expiry-polish`, but that branch was
never merged into `dev`. Current `dev` therefore still referenced the missing
`common.cancel` and `common.create` keys. A page-level DOM regression test
reproduced the exact raw-key output before the fix.

## Implemented behavior

- The create dialog uses `dialog.cancel` and
  `servicePrincipals.create` in all three supported locales.
- Token-name input and rows preserve long names without hiding actions.
- Expiring service tokens default to 90 days and may be valid for at most three
  calendar years, enforced by both frontend and backend.
- Platform Admins can explicitly select Never Expires. The UI sends
  `expiresAt: null`; omission of the property still receives HTTP 422.
- A never-expiring token stays valid until revoked or the service principal is
  disabled.
- Active-token summaries include never-expiring tokens while nearest expiry
  only represents dated active tokens.
- Create, rotate, revoke, disable, audit, one-time secret, hashing, and
  `source:import` scope behavior remain unchanged.

## Schema and API

- Added Python-owned local migration
  `20260824_01__service_token_optional_expiry.sql`.
- The migration only drops `NOT NULL` from `service_token.expires_at`.
- Create and rotate request schemas require `expiresAt` and accept a timestamp
  or explicit null.
- Regenerated the checked-in Service Principal OpenAPI JSON and TypeScript
  schema.
- No new environment variables are required.

## TDD evidence

The following tracer bullets were observed red before implementation and green
afterward:

- Page test could only find `common.cancel` and `common.create`.
- Domain/API tests rejected null expiry and the old one-year rule rejected the
  three-year boundary.
- Migration baseline test could not find `20260824_01`.
- Frontend expiry helper and token controls did not exist.
- Locale coverage could not find expiry and Never Expires keys.

## Verification results

### Backend

- Focused real-PostgreSQL service-account suite: `30 passed`.
- Broader focused backend/docs suite: `31 passed, 2 skipped` when PostgreSQL was
  not exported for that secondary run.
- Complete backend suite with real PostgreSQL:
  `1632 passed, 11 skipped, 1 existing warning`.
- Ruff on all changed backend modules and tests: passed.
- Production backend image build: passed.
- Running migrations from the production image against PostgreSQL: passed and
  returned `skillhub_flyway_v43_baseline`.

### Frontend

- Focused Vitest tests: `10 passed` before the final browser coverage.
- Complete Vitest suite: `226 files, 919 tests passed`.
- TypeScript typecheck: passed.
- ESLint: passed.
- Production Vite build: passed with only existing browsers-list and chunk-size
  warnings.
- Production frontend image build: passed.

### Real browser and services

- Real Vite/backend flow: Platform Admin created and revoked a Never Expires
  token successfully.
- Production root deployment: `2 passed`.
- Production `/skillhub` deployment with matching backend/public base-path
  contract: `2 passed`.
- Browser coverage switched among English, Traditional Chinese, and Simplified
  Chinese and verified the create-dialog labels and hints.
- The workflow used real PostgreSQL and backend sessions. Scanner health was
  `healthy`; Redis and MinIO were reachable.
- Root and subpath backend logs contained 173 observed HTTP requests with zero
  5xx, traceback, exception, or SQL-error lines.
- A test principal left active by an intentionally failing selector run was
  revoked and disabled through the management API; no active test token was
  left behind.

### Deployment and repository checks

- `kubectl kustomize deploy/k8s/base`: passed.
- `kubectl kustomize deploy/k8s/overlays/external`: passed.
- Release Compose config: passed.
- `git diff --check`: passed; Windows line-ending notices only.

## Non-blocking existing warnings

- Starlette TestClient deprecation warning.
- Browserslist data-age warning.
- Existing large Vite chunk warning.
- Playwright `NO_COLOR`/`FORCE_COLOR` warning.

## Files for follow-up

- Design:
  `docs/backend-python-maintenance/specs/2026-08-24-service-account-never-expired-design.md`
- Plan:
  `docs/backend-python-maintenance/plans/2026-08-24-service-account-never-expired.md`
- Operator SOP: `deploy/k8s/oss-github-source-import.zh.md`
