# Service Account Never-Expired Token Implementation Plan

Date: 2026-08-24

Status: implemented and verified

Branch: `codex/service-account-never-expired`

Baseline: `2edbda1cfce505f3de824290752e033be18a1195`

Design:
`docs/backend-python-maintenance/specs/2026-08-24-service-account-never-expired-design.md`

## Phase 1: Preserve the missing UI fixes

Implement the create-dialog translation correction, three-language locale
coverage, long token-name layout, and three-calendar-year validation from the
unmerged historical branch on top of current `dev`.

Success criteria:

- The page regression test no longer finds `common.cancel` or `common.create`.
- English, Simplified Chinese, and Traditional Chinese contain all Service
  Accounts keys.
- Token names up to the backend limit remain readable and actions remain
  visible.
- Expiring dates outside the three-calendar-year range are blocked before the
  mutation and rejected by the backend.

## Phase 2: Add the explicit never-expired contract

Add a nullable-expiry local migration, update service-account contracts,
repository/auth queries, request models, response types, and generated OpenAPI
artifacts. Preserve required-property semantics by requiring `expiresAt` while
allowing its value to be null.

Success criteria:

- Missing `expiresAt` receives HTTP 422.
- Explicit `expiresAt: null` creates or rotates a token successfully.
- PostgreSQL stores `NULL` and returns `expiresAt: null`.
- Authentication accepts an unrevoked null-expiry token and rejects it after
  revocation or principal disablement.
- All writes retain current authorization, audit, transaction, and rollback
  behavior.

## Phase 3: Add the Platform Admin UI

Add an explicit Never Expires control to token creation/rotation. Keep the
90-day expiry default. Disable date validation only while Never Expires is
selected, send explicit null, show the localized security warning, and render
null expiry as Never Expires in token rows.

Success criteria:

- The UI cannot accidentally submit a never-expiring token by omitting a
  field.
- Expiring and never-expiring create/rotate flows both work.
- All new text exists in the three supported locales.
- Typecheck, lint, and focused Vitest tests pass.

## Phase 4: Real-service and deployment verification

Run migrations and the complete workflow with PostgreSQL, Redis, MinIO,
scanner, backend, and production frontend. Test both root and `/skillhub`
paths with an authenticated Platform Admin.

Required checks:

```powershell
cd server-python
uv run --no-cache pytest tests/test_service_accounts.py tests/test_admin_service_principals_api.py tests/test_service_accounts_postgres.py tests/test_service_principal_schema_postgres.py tests/test_auth_service_tokens.py -q
uv run --no-cache pytest tests -q
uv run python -m app.migrations upgrade

cd ../web
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build

cd ..
docker build -t skillhub-server-python:service-token-verify -f server-python/Dockerfile .
kubectl kustomize deploy/k8s/base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

Browser acceptance:

1. Open Create Service Principal in each supported language and confirm both
   action labels are translated.
2. Open Manage Tokens and confirm a long name remains readable.
3. Create a 90-day token and a maximum three-year token.
4. Select Never Expires, confirm the warning, create a token, and verify the
   list shows Never Expires.
5. Authenticate a source-import request with the persistent token, revoke it,
   and confirm the same token is rejected.
6. Repeat navigation and critical UI checks under `/skillhub`.
7. Inspect backend and scanner logs for HTTP 5xx, tracebacks, and SQL errors.

## Docs to update

- `deploy/k8s/oss-github-source-import.zh.md`
- The implementation result under
  `docs/backend-python-maintenance/results/`
- Generated Service Principal OpenAPI JSON and TypeScript types

## Explicit non-goals

- Personal API tokens
- New service-token scopes
- Automatic expiry changes for existing tokens
- New deployment environment variables
- Java or hybrid backend work
