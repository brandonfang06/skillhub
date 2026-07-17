# Product Suite Namespace Admin Daily Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an idempotent daily Python command that loads product-suite owners from an internal PIC source module and grants existing Keycloak users namespace `ADMIN`, with operator documentation and optional Kubernetes CronJob manifests.

**Architecture:** Keep the organization-specific PIC client outside the upstream-following repository behind a small async Python source contract. The shared command validates the complete source snapshot, reconciles existing `identity_binding` and `namespace_member` rows in one transaction, supports dry-run, and returns structured JSON; a separately applied CronJob invokes it once per day.

**Tech Stack:** Python 3.12, SQLAlchemy async, argparse, importlib, pytest, uv, Kubernetes CronJob, Kustomize

---

## File Structure

### Python Source

- Create `server-python/app/integrations/__init__.py`: organization integration package marker.
- Create `server-python/app/integrations/product_suite/__init__.py`: public source and reconciliation exports.
- Create `server-python/app/integrations/product_suite/contracts.py`: immutable source config, owner record, issue, and summary types plus normalization/validation.
- Create `server-python/app/integrations/product_suite/source.py`: environment/CLI config resolution and trusted dynamic source-module loading.
- Create `server-python/app/integrations/product_suite/repository.py`: namespace, Keycloak identity, and membership reconciliation transaction.
- Create `server-python/app/integrations/product_suite/cli.py`: source invocation, engine lifecycle, JSON output, and exit-code policy.
- Create `server-python/app/integrations/product_suite/__main__.py`: `python -m` entry point.

### Tests

- Create `server-python/tests/test_product_suite_source.py`: contracts, snapshot validation, env/CLI precedence, and source loading.
- Create `server-python/tests/test_product_suite_reconciliation.py`: database outcome, dry-run, idempotency, and rollback behavior.
- Create `server-python/tests/test_product_suite_cli.py`: command output, exit codes, and engine disposal.
- Create `server-python/tests/support/product_suite_source.py`: importable async source fixture.
- Create `server-python/tests/test_product_suite_sync_deployment.py`: Docker, Kustomize, plain YAML, and documentation contract.

### Operator Documentation And Deployment

- Create `server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`: complete Traditional Chinese PIC integration and operation manual.
- Modify `server-python/README.md`: link to the operation manual.
- Modify `server-python/ENVIRONMENT_VARIABLES.md`: add shared sync variables and distinguish PIC-private credentials.
- Create `deploy/k8s/addons/product-suite-admin-sync/kustomization.yaml`: optional addon entry point.
- Create `deploy/k8s/addons/product-suite-admin-sync/cronjob.yaml`: daily CronJob using the backend image.
- Create `deploy/k8s/addons/product-suite-admin-sync/secret.yaml.example`: PIC-private environment example.
- Create `deploy/k8s/addons/product-suite-admin-sync/README.md`: Kustomize deployment instructions.
- Create `deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example`: plain optional CronJob example.
- Modify `deploy/k8s/README.md`: document optional addon.
- Modify `deploy/k8s/plain/README.md`: document copying and applying the plain example separately.

## Exit Code Contract

| Code | Meaning |
| --- | --- |
| `0` | Sync completed; `waitingForLogin` may be nonzero, but no operator action is required |
| `1` | Sync committed valid changes but found blocked namespaces/users or identity conflicts |
| `2` | Configuration, source loading/fetching, snapshot validation, or database transaction failed |

## Task 1: Source Contract And Configuration

**Files:**
- Create: `server-python/tests/test_product_suite_source.py`
- Create: `server-python/tests/support/product_suite_source.py`
- Create: `server-python/app/integrations/__init__.py`
- Create: `server-python/app/integrations/product_suite/__init__.py`
- Create: `server-python/app/integrations/product_suite/contracts.py`
- Create: `server-python/app/integrations/product_suite/source.py`

- [ ] **Step 1: Write failing contract and normalization tests**

Add tests that define the required source shape:

```python
def test_owner_record_normalizes_windows_account() -> None:
    record = ProductSuiteOwnerRecord.create(
        external_suite_id=" suite-1 ",
        namespace_slug=" product-a ",
        owner_windows_account=" HCFange ",
    )

    assert record.external_suite_id == "suite-1"
    assert record.namespace_slug == "product-a"
    assert record.owner_windows_account == "HCFange"
    assert record.normalized_windows_account == "hcfange"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_suite_id", ""),
        ("namespace_slug", ""),
        ("owner_windows_account", ""),
        ("namespace_slug", "n" * 65),
        ("owner_windows_account", "u" * 129),
    ],
)
def test_owner_record_rejects_invalid_boundaries(field: str, value: str) -> None:
    values = {
        "external_suite_id": "suite-1",
        "namespace_slug": "product-a",
        "owner_windows_account": "hcfange",
    }
    values[field] = value

    with pytest.raises(ProductSuiteSourceError):
        ProductSuiteOwnerRecord.create(**values)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd server-python
uv --cache-dir .uv-cache run pytest tests/test_product_suite_source.py -q
```

Expected: collection fails because `app.integrations.product_suite` does not exist.

- [ ] **Step 3: Implement immutable contracts and snapshot validation**

Implement these public types:

```python
@dataclass(frozen=True)
class ProductSuiteSourceConfig:
    api_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class ProductSuiteOwnerRecord:
    external_suite_id: str
    namespace_slug: str
    owner_windows_account: str
    normalized_windows_account: str

    @classmethod
    def create(
        cls,
        *,
        external_suite_id: str,
        namespace_slug: str,
        owner_windows_account: str,
    ) -> "ProductSuiteOwnerRecord":
        ...


@dataclass(frozen=True)
class ProductSuiteSyncIssue:
    external_suite_id: str
    namespace_slug: str
    owner_windows_account: str
    code: str
    detail: str


@dataclass
class ProductSuiteSyncSummary:
    suites_fetched: int = 0
    namespaces_resolved: int = 0
    administrators_added: int = 0
    members_promoted: int = 0
    memberships_unchanged: int = 0
    waiting_for_login: int = 0
    blocked: int = 0
    identity_conflicts: int = 0
    issues: list[ProductSuiteSyncIssue] = field(default_factory=list)
    dry_run: bool = False
```

`validate_snapshot(...)` must reject:

- an empty snapshot;
- duplicate `external_suite_id`;
- duplicate `namespace_slug`;
- a non-record return value.

- [ ] **Step 4: Write failing environment and module-loader tests**

Cover:

```python
def test_sync_config_uses_cli_over_environment() -> None:
    config = product_suite_sync_config(
        [
            "--source-module", "company.pic_api",
            "--api-url", "https://cli.example/api",
            "--timeout-seconds", "12",
            "--identity-provider", "company-keycloak",
            "--dry-run",
        ],
        environ={
            "SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE": "env.pic_api",
            "SKILLHUB_PRODUCT_SUITE_API_URL": "https://env.example/api",
        },
    )

    assert config.source_module == "company.pic_api"
    assert config.source.api_url == "https://cli.example/api"
    assert config.source.timeout_seconds == 12
    assert config.identity_provider == "company-keycloak"
    assert config.dry_run is True


@pytest.mark.anyio
async def test_load_source_calls_internal_async_module() -> None:
    fetcher = load_product_suite_source("tests.support.product_suite_source")
    records = await fetcher(ProductSuiteSourceConfig("https://pic.test/api", 30))

    assert records[0].namespace_slug == "product-a"
```

- [ ] **Step 5: Implement configuration and trusted module loading**

Add:

```python
@dataclass(frozen=True)
class ProductSuiteSyncConfig:
    source_module: str
    source: ProductSuiteSourceConfig
    identity_provider: str
    dry_run: bool


def load_product_suite_source(module_name: str) -> ProductSuiteSource:
    module = importlib.import_module(module_name)
    fetcher = getattr(module, "fetch_product_suite_owners", None)
    if fetcher is None or not callable(fetcher):
        raise ProductSuiteSourceError(
            f"{module_name} must define fetch_product_suite_owners(config)"
        )
    return fetcher
```

Require nonblank source module and API URL, a positive timeout no greater than
300 seconds, and a nonblank identity provider. Support:

```text
SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE
SKILLHUB_PRODUCT_SUITE_API_URL
SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS
SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER
```

- [ ] **Step 6: Verify Task 1 GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_product_suite_source.py -q
```

Expected: all source contract tests pass.

- [ ] **Step 7: Commit Task 1**

Commit:

```text
feat: define product suite sync source contract
```

## Task 2: Membership Reconciliation

**Files:**
- Create: `server-python/tests/test_product_suite_reconciliation.py`
- Create: `server-python/app/integrations/product_suite/repository.py`
- Modify: `server-python/app/integrations/product_suite/__init__.py`

- [ ] **Step 1: Write failing happy-path and dry-run tests**

Use a stateful fake SQLAlchemy connection and verify:

```python
@pytest.mark.anyio
async def test_reconcile_adds_and_promotes_product_suite_admins() -> None:
    connection = ProductSuiteConnection(
        namespaces={"product-a": namespace_row(id=10), "product-b": namespace_row(id=20)},
        identities={
            ("keycloak", "hcfange"): user_identity("user-a"),
            ("keycloak", "alice"): user_identity("user-b"),
        },
        memberships={(20, "user-b"): "MEMBER"},
    )

    summary = await reconcile_product_suite_admins(
        FakeEngine(connection),
        records=[
            owner_record("suite-a", "product-a", "hcfange"),
            owner_record("suite-b", "product-b", "alice"),
        ],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert connection.memberships[(10, "user-a")] == "ADMIN"
    assert connection.memberships[(20, "user-b")] == "ADMIN"
    assert summary.administrators_added == 1
    assert summary.members_promoted == 1


@pytest.mark.anyio
async def test_reconcile_dry_run_reports_without_writing() -> None:
    ...
    assert summary.dry_run is True
    assert summary.administrators_added == 1
    assert connection.memberships == {}
```

- [ ] **Step 2: Run reconciliation tests and verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_product_suite_reconciliation.py -q
```

Expected: import fails because `repository.py` does not exist.

- [ ] **Step 3: Implement transactional reconciliation**

Implement:

```python
async def reconcile_product_suite_admins(
    engine: Any,
    *,
    records: Sequence[ProductSuiteOwnerRecord],
    identity_provider: str,
    dry_run: bool,
) -> ProductSuiteSyncSummary:
    validated = validate_snapshot(records)
    summary = ProductSuiteSyncSummary(
        suites_fetched=len(validated),
        dry_run=dry_run,
    )
    async with engine.begin() as connection:
        for record in validated:
            await _reconcile_record(
                connection,
                record=record,
                identity_provider=identity_provider,
                dry_run=dry_run,
                summary=summary,
            )
    return summary
```

SQL boundaries:

```sql
SELECT id, slug, status, type
FROM namespace
WHERE slug = :slug
LIMIT 1
```

```sql
SELECT ib.user_id, ib.login_name, ua.status, ua.merged_to_user_id
FROM identity_binding ib
JOIN user_account ua ON ua.id = ib.user_id
WHERE ib.provider_code = :provider_code
  AND LOWER(BTRIM(ib.login_name)) = LOWER(:login_name)
ORDER BY ib.id ASC
```

```sql
SELECT role
FROM namespace_member
WHERE namespace_id = :namespace_id
  AND user_id = :user_id
LIMIT 1
```

For missing membership:

```sql
INSERT INTO namespace_member (namespace_id, user_id, role)
VALUES (:namespace_id, :user_id, 'ADMIN')
ON CONFLICT (namespace_id, user_id) DO NOTHING
```

For `MEMBER`:

```sql
UPDATE namespace_member
SET role = 'ADMIN',
    updated_at = CURRENT_TIMESTAMP
WHERE namespace_id = :namespace_id
  AND user_id = :user_id
  AND role = 'MEMBER'
```

If an insert or promotion loses a concurrency race, re-read the role and
converge without failing.

- [ ] **Step 4: Write failing boundary tests**

Cover these exact outcomes:

- no identity -> `waiting_for_login`, exit attention remains false;
- two active identity rows -> `IDENTITY_CONFLICT`;
- disabled or merged user -> `USER_BLOCKED`;
- missing namespace -> `NAMESPACE_NOT_FOUND`;
- frozen or archived namespace -> `NAMESPACE_BLOCKED`;
- existing `ADMIN` and `OWNER` -> unchanged;
- repeated snapshot -> no duplicate insert/update;
- a database exception exits the transaction and propagates.

- [ ] **Step 5: Implement boundary classifications**

Use stable issue codes and do not include secrets:

```text
IDENTITY_CONFLICT
USER_BLOCKED
NAMESPACE_NOT_FOUND
NAMESPACE_BLOCKED
```

`waitingForLogin` is a normal summary count and is not added to `issues`.
Unknown, frozen, archived, disabled, merged, and conflict records are skipped
without preventing valid records in the same snapshot from converging.

- [ ] **Step 6: Verify Task 2 GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest `
  tests/test_product_suite_source.py `
  tests/test_product_suite_reconciliation.py -q
```

Expected: all source and reconciliation tests pass.

- [ ] **Step 7: Commit Task 2**

Commit:

```text
feat: reconcile product suite namespace admins
```

## Task 3: Command Lifecycle And Structured Output

**Files:**
- Create: `server-python/tests/test_product_suite_cli.py`
- Create: `server-python/app/integrations/product_suite/cli.py`
- Create: `server-python/app/integrations/product_suite/__main__.py`

- [ ] **Step 1: Write failing CLI tests**

Inject source loader and engine factory seams:

```python
@pytest.mark.anyio
async def test_run_sync_outputs_summary_and_disposes_engine() -> None:
    engine = DisposableFakeEngine(...)

    result = await run_product_suite_sync(
        config=sync_config(),
        source_loader=lambda _: successful_source,
        engine_factory=lambda _: engine,
    )

    assert result.exit_code == 0
    assert result.summary.waiting_for_login == 1
    assert engine.disposed is True


@pytest.mark.anyio
async def test_run_sync_returns_two_without_database_writes_when_source_fails() -> None:
    ...
    assert result.exit_code == 2
    assert connection.statements == []
```

Also verify blocked/conflict outcomes return `1`, while only
`waitingForLogin` returns `0`.

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_product_suite_cli.py -q
```

Expected: import fails because CLI files do not exist.

- [ ] **Step 3: Implement command lifecycle**

Implement:

```python
async def run_product_suite_sync(
    *,
    config: ProductSuiteSyncConfig,
    source_loader: SourceLoader = load_product_suite_source,
    engine_factory: EngineFactory = create_database_engine,
) -> ProductSuiteCommandResult:
    engine = None
    try:
        fetcher = source_loader(config.source_module)
        records = await fetcher(config.source)
        validated = validate_snapshot(records)
        settings = get_settings()
        engine = engine_factory(settings)
        summary = await reconcile_product_suite_admins(
            engine,
            records=validated,
            identity_provider=config.identity_provider,
            dry_run=config.dry_run,
        )
        return ProductSuiteCommandResult.from_summary(summary)
    except Exception as exc:
        return ProductSuiteCommandResult.fatal(str(exc))
    finally:
        if engine is not None:
            await dispose_database_engine(engine)
```

`main()` parses args, runs the async function, writes exactly one JSON object
to stdout, writes fatal diagnostics to stderr, and returns the exit code.
Source-module, source-fetch, validation, engine, and database exceptions all
map to fatal exit code `2`; the command boundary must not leak an unstructured
traceback from an expected CronJob run.

- [ ] **Step 4: Verify `python -m` entry point**

Run:

```powershell
uv --cache-dir .uv-cache run python -m app.integrations.product_suite --help
```

Expected: exit `0` and help lists source module, API URL, timeout, identity
provider, and dry-run options.

- [ ] **Step 5: Verify Task 3 GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest `
  tests/test_product_suite_source.py `
  tests/test_product_suite_reconciliation.py `
  tests/test_product_suite_cli.py -q
```

Expected: all product-suite sync tests pass.

- [ ] **Step 6: Commit Task 3**

Commit:

```text
feat: add product suite admin sync command
```

## Task 4: Traditional Chinese Integration Manual

**Files:**
- Create: `server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`
- Modify: `server-python/README.md`
- Modify: `server-python/ENVIRONMENT_VARIABLES.md`

- [ ] **Step 1: Write the complete operator manual**

Document:

- why users must log in once before a daily sync can resolve their UUID;
- the `fetch_product_suite_owners(config)` contract;
- a complete internal PIC module example;
- required record fields;
- internal image packaging;
- all shared environment variables;
- how the internal module reads its own Secret-backed credentials;
- local `uv` dry-run and real execution;
- JSON summary fields and exit codes;
- daily delay behavior;
- owner-change behavior;
- troubleshooting for import errors, missing users, unknown namespaces,
  conflicts, disabled users, and database rollback.

The example module must be directly adaptable:

```python
from collections.abc import Sequence

import httpx

from app.integrations.product_suite import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
)


async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(
            config.api_url,
            headers={"Authorization": f"Bearer {read_pic_token()}"},
        )
        response.raise_for_status()
        payload = response.json()

    return [
        ProductSuiteOwnerRecord.create(
            external_suite_id=item["productSuiteId"],
            namespace_slug=item["namespaceSlug"],
            owner_windows_account=item["ownerWindowsAccount"],
        )
        for item in payload["items"]
    ]
```

State explicitly that `httpx` is a development dependency in the public
project; an organization module using it in the production image must add it
to the organization image/dependencies, or use the Python standard library or
another installed HTTP client.

- [ ] **Step 2: Add README and environment links**

Link the manual from `server-python/README.md`. Add this table to
`server-python/ENVIRONMENT_VARIABLES.md`:

```text
SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE
SKILLHUB_PRODUCT_SUITE_API_URL
SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS
SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER
```

Do not prescribe PIC token variable names because they belong to the internal
module.

- [ ] **Step 3: Verify documentation**

Run:

```powershell
rg -n "SKILLHUB_PRODUCT_SUITE_|fetch_product_suite_owners|waitingForLogin|dry-run" `
  server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md `
  server-python/ENVIRONMENT_VARIABLES.md `
  server-python/README.md
git diff --check
```

Expected: every shared variable and operating boundary is documented, with no
whitespace errors.

- [ ] **Step 4: Commit Task 4**

Commit:

```text
docs: document product suite admin synchronization
```

## Task 5: Optional Kustomize And Plain CronJob Manifests

**Files:**
- Create: `server-python/tests/test_product_suite_sync_deployment.py`
- Create: `deploy/k8s/addons/product-suite-admin-sync/kustomization.yaml`
- Create: `deploy/k8s/addons/product-suite-admin-sync/cronjob.yaml`
- Create: `deploy/k8s/addons/product-suite-admin-sync/secret.yaml.example`
- Create: `deploy/k8s/addons/product-suite-admin-sync/README.md`
- Create: `deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example`
- Modify: `deploy/k8s/README.md`
- Modify: `deploy/k8s/plain/README.md`

- [ ] **Step 1: Write failing deployment contract tests**

Assert:

```python
def test_product_suite_sync_cronjob_is_optional_and_daily() -> None:
    cronjob = read("deploy/k8s/addons/product-suite-admin-sync/cronjob.yaml")
    base = read("deploy/k8s/base/kustomization.yaml")

    assert "kind: CronJob" in cronjob
    assert 'schedule: "0 2 * * *"' in cronjob
    assert "concurrencyPolicy: Forbid" in cronjob
    assert "uv" in cronjob
    assert "-m" in cronjob
    assert "app.integrations.product_suite" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_API_URL" in cronjob
    assert "product-suite-admin-sync/cronjob.yaml" not in base
```

Also assert the plain manifest remains `.yaml.example` so
`kubectl apply -f deploy/k8s/plain/backend/` does not enable the CronJob
implicitly.

- [ ] **Step 2: Run deployment tests and verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_product_suite_sync_deployment.py -q
```

Expected: fails because addon and plain example files do not exist.

- [ ] **Step 3: Implement optional manifests**

The CronJob must:

- use `batch/v1`;
- default to `schedule: "0 2 * * *"`;
- set `concurrencyPolicy: Forbid`;
- set `successfulJobsHistoryLimit: 3` and `failedJobsHistoryLimit: 5`;
- use `backoffLimit: 2`;
- set `restartPolicy: Never`;
- use the Python backend image;
- invoke `uv run python -m app.integrations.product_suite`;
- read `SKILLHUB_DATABASE_URL` from `skillhub-secret/database-url`;
- set the four shared source variables;
- import PIC-private credentials through
  `envFrom.secretRef.name: skillhub-product-suite-sync-secret`.

The addon must not be referenced from `deploy/k8s/base/kustomization.yaml`.
The operator opts in with:

```powershell
kubectl apply -k deploy/k8s/addons/product-suite-admin-sync
```

The plain example is copied and edited before:

```powershell
kubectl -n skillhub apply -f deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml
```

- [ ] **Step 4: Add K8s documentation**

Document:

- the internal derivative image requirement;
- source module and API URL customization;
- creating the PIC Secret;
- schedule/time-zone implications;
- dry-run Job creation from the CronJob;
- log inspection;
- suspend and delete commands;
- the fact that the backend Deployment does not run this scheduler.

- [ ] **Step 5: Verify manifest rendering**

Run:

```powershell
kubectl kustomize deploy/k8s/addons/product-suite-admin-sync
kubectl apply --dry-run=client --validate=false `
  -f deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example
uv --cache-dir .uv-cache run pytest tests/test_product_suite_sync_deployment.py -q
```

Expected: Kustomize renders one CronJob, client dry-run accepts the plain
example, and deployment tests pass.

- [ ] **Step 6: Commit Task 5**

Commit:

```text
deploy: add optional product suite admin sync
```

## Task 6: Full Verification And Review

**Files:**
- Modify only files identified by findings from review.

- [ ] **Step 1: Run focused verification**

```powershell
cd server-python
uv --cache-dir .uv-cache run pytest `
  tests/test_product_suite_source.py `
  tests/test_product_suite_reconciliation.py `
  tests/test_product_suite_cli.py `
  tests/test_product_suite_sync_deployment.py -q
```

- [ ] **Step 2: Run full backend verification**

```powershell
uv --cache-dir .uv-cache run pytest tests -q
```

- [ ] **Step 3: Verify command and documentation**

```powershell
uv --cache-dir .uv-cache run python -m app.integrations.product_suite --help
rg -n "SKILLHUB_PRODUCT_SUITE_|fetch_product_suite_owners|waitingForLogin|dry-run" `
  PRODUCT_SUITE_ADMIN_SYNC.zh.md `
  ENVIRONMENT_VARIABLES.md `
  README.md
```

- [ ] **Step 4: Verify image and Kubernetes artifacts**

From repository root:

```powershell
docker build -t skillhub-server-python:product-suite-sync -f server-python/Dockerfile .
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/addons/product-suite-admin-sync
kubectl apply --dry-run=client --validate=false `
  -f deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example
```

- [ ] **Step 5: Review the complete diff**

Confirm:

- no database migration;
- no OAuth code;
- no frontend or generated OpenAPI changes;
- no PIC response parser or credentials in the public repository;
- membership writes only insert/promote `ADMIN`;
- `OWNER` is never changed;
- dry-run performs no writes;
- source/config failure occurs before DB writes;
- transaction failure rolls back all membership writes;
- optional manifests are not enabled by base/plain directory application.

- [ ] **Step 6: Run final hygiene checks**

```powershell
git diff --check
git status --short
```

- [ ] **Step 7: Commit review fixes, push, and report**

Use narrowly scoped commits for any review fixes. Push
`codex/product-suite-admin-provisioning` only after all gates pass.
