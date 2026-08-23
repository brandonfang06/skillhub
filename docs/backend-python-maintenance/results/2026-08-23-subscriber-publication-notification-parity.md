# Subscriber publication notification parity verification

Date: 2026-08-23

Branch: `codex/upstream-v0.2.17-risk-first`

Baseline: `9f1bbdb5fc94388a4984f9f8c4cbe9479ad8a7ff`

Plan: `docs/backend-python-maintenance/plans/2026-08-23-subscriber-publication-notification-parity.md`

## Delivered behavior

- Every supported transition that commits a version as `PUBLISHED` now uses one
  common publication-outcome contract:
  - normal review approval;
  - authorized direct auto-publish;
  - private confirm-publish;
  - promotion materialization.
- Search projection and durable notification rows are written in the same
  database transaction as the publication mutation.
- SSE fanout starts only after commit and remains best-effort. An SSE failure
  cannot roll back or erase the durable notification-center row.
- Enabled subscribers receive `SUBSCRIPTION_NEW_VERSION`; the publication actor
  and users with `PUBLISH / IN_APP` disabled are excluded.
- Existing owner `SKILL_PUBLISHED`, review-decision, promotion-governance,
  authorization, audit, ownership, and API response behavior are preserved.
- Pending review, private upload, rejected, and rolled-back versions do not emit
  publication notifications.
- No schema migration, API contract change, new environment variable, Java,
  Maven, Spring Boot, or hybrid runtime was introduced.

## Automated verification

### Focused workflow tests

```powershell
uv run --no-cache pytest tests/test_publish_publication_outcomes.py tests/test_skill_lifecycle_confirm_publish.py tests/test_review_approve.py tests/test_publish_orchestration.py tests/test_promotion_write.py -q
```

Result: `66 passed, 1 existing Starlette warning`.

The new TDD tracers first failed on the missing review, auto-publish, confirm,
and promotion seams, then passed after the transaction-aware wiring was added.

### Real PostgreSQL publication paths

```powershell
$env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_dev@127.0.0.1:5432/skillhub'
uv run --no-cache pytest tests/test_skill_lifecycle_confirm_publish_postgres.py tests/test_publication_notification_paths_postgres.py -q
```

Result: `7 passed`.

The database-backed tests prove enabled and disabled preferences, actor
exclusion, owner semantics, replay/concurrency behavior, rollback, search
projection, direct auto-publish, reviewed publication, and promotion
materialization against PostgreSQL.

### Complete Python backend

```powershell
$env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_dev@127.0.0.1:5432/skillhub'
$env:SKILLHUB_TEST_REDIS_URL='redis://127.0.0.1:6379/0'
uv run --no-cache pytest tests -q
```

Result: `1640 passed, 7 warnings in 241.00s`. The warnings are the existing
Starlette and Redis `setex` deprecations.

### Web

```powershell
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build
```

Results:

- Typecheck and lint passed.
- Vitest: `223` files and `909` tests passed.
- Production build passed with the existing chunk-size and stale browsers-list
  warnings.

### Real authenticated browser

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:3100'
.\node_modules\.bin\playwright.CMD test e2e/skill-subscription.spec.ts --project=chromium
```

Result: `3 passed`.

The new scenario used separate owner, subscriber, and admin sessions. It
verified a live unread badge after `1.1.0` approval, durable notification after
refresh, skill-detail navigation, exact skill/version display, and no `1.2.0`
notification after disabling Publish Notifications.

## Integrated runtime acceptance

The following dependencies were running together throughout the real-browser
acceptance:

- PostgreSQL;
- Redis;
- MinIO;
- Python scanner;
- Python backend with `SKILLHUB_SCAN_CONSUMER_ENABLED=true`;
- web frontend.

The backend log showed the real chain
`publish -> Redis enqueue -> scan consumer -> scanner /scan-upload -> PostgreSQL
PENDING_REVIEW -> review approval`, with scanner verdict `SAFE`. Notification
SSE and list/unread APIs returned HTTP 200 and no backend traceback, SQL error,
or HTTP 5xx was observed.

The production web image was started twice against the same verified backend:

| Route model | URL | Result |
| --- | --- | --- |
| Root | `http://127.0.0.1:3101` | Authenticated notification settings and SSE passed |
| Sub-path | `http://127.0.0.1:3102/skillhub` | Authenticated notification settings and prefixed SSE passed |

Both checks had no application console error, page exception, failed API
response, 5xx, doubled prefix, or root-path escape. The only browser noise was
the existing CSP meta warning and blocked external Google Fonts request in the
restricted test environment.

## Release and deployment checks

The following production images built successfully:

- `skillhub-server-python:subscriber-notification-verify`
- `skillhub-web:subscriber-notification-verify`

These checks also passed:

```powershell
docker compose -f docker-compose.yml config --quiet
docker compose --env-file .env.release.example -f compose.release.yml config --quiet
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/external
git diff --check
```

## Handoff status

Implementation and verification are complete in the isolated worktree. No
commit, push, merge, deployment, or pull request was performed.
