# Product Suite Namespace Admin Sync Result

- **Date:** 2026-07-17
- **Branch:** `codex/product-suite-admin-provisioning`
- **Status:** Complete

## Delivered

- Isolated async source-module contract under
  `server-python/app/integrations/product_suite/`.
- Idempotent PostgreSQL reconciliation that only inserts namespace `ADMIN` or
  promotes `MEMBER` to `ADMIN`.
- Dry-run, structured one-line JSON, stable exit codes, source timeout, and
  engine disposal.
- Traditional Chinese integration and operation manual:
  `server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`.
- Optional Kustomize addon and plain CronJob example.
- Focused source, transaction, CLI, deployment, and rollback tests.

No database migration, OAuth callback, HTTP API, frontend, generated OpenAPI,
or organization-specific PIC parser was added.

## Review Findings Fixed

1. Aligned the Secret example name with the CronJob reference.
2. Converted argparse failures to fatal JSON instead of leaking `SystemExit`
   usage output.
3. Enforced the configured source timeout in the shared command so an internal
   module has a bounded fetch window.
4. Added `uv run --no-sync` to container commands after image verification
   showed plain `uv run` downloading development packages at runtime.
5. Moved owner-record normalization into the dataclass invariant so an internal
   source cannot construct mismatched display and lookup accounts.
6. Added a 900-second Kubernetes Job deadline so a stuck source cancellation or
   database connection cannot block future `concurrencyPolicy: Forbid` runs.

## Verification

### Automated tests

```powershell
cd server-python
uv --cache-dir .uv-cache run pytest tests -q
```

Result: `981 passed, 1 warning in 107.38s`. The warning is the existing
Starlette `TestClient` / `httpx` deprecation warning.

Focused product-suite verification:

```powershell
uv --cache-dir .uv-cache run pytest `
  tests/test_product_suite_source.py `
  tests/test_product_suite_reconciliation.py `
  tests/test_product_suite_cli.py `
  tests/test_product_suite_sync_deployment.py -q
```

Result: `49 passed in 0.70s`.

### Production image

```powershell
docker build `
  -t skillhub-server-python:product-suite-review `
  -f server-python/Dockerfile .

docker run --rm skillhub-server-python:product-suite-review `
  uv run --no-sync python -m app.integrations.product_suite --help
```

Result: image build completed and the command exposed source module, API URL,
timeout, identity provider, and dry-run options without downloading packages.
An additional in-image smoke check confirmed direct record construction enforces
trimmed fields and the case-folded Windows-account lookup invariant.

### Kubernetes

```powershell
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/addons/product-suite-admin-sync
```

Result: base still rendered the original frontend/backend/scanner workloads;
the addon independently rendered one `batch/v1` CronJob using the organization
image placeholder, `uv run --no-sync`, and `activeDeadlineSeconds: 900`.

The plain `.yaml.example` was parsed offline with PyYAML and confirmed as one
valid CronJob with the same 900-second deadline.
`kubectl apply --dry-run=client` could not be used without Kubernetes API
discovery in this local environment.

### Real PostgreSQL transaction

An ephemeral PostgreSQL 16 container was initialized with the complete SkillHub
schema through `python -m app.migrations upgrade`. One ACTIVE TEAM namespace
and one active Keycloak identity were seeded.

Observed command results:

```text
dry-run: administratorsAdded=1, database membership count=0
first sync: administratorsAdded=1
second sync: membershipsUnchanged=1
database role: ADMIN
```

The disposable container was stopped and removed after verification.

### Final hygiene

```powershell
git diff --check
git diff --name-only dev...HEAD
```

Result: no whitespace errors and no changes under schema migration, OAuth,
HTTP API, frontend, or generated OpenAPI paths.

## Internal PIC Handoff

The organization integration must provide:

```python
async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    ...
```

Build that module and all production HTTP dependencies into the organization
backend image. Then configure the four `SKILLHUB_PRODUCT_SUITE_*` variables and
the module's private Secret-backed credentials as documented in
`server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`.
