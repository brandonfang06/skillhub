from __future__ import annotations

import pytest

from app.integrations.product_suite.contracts import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
    ProductSuiteSourceError,
    validate_snapshot,
)
from app.integrations.product_suite.source import (
    load_product_suite_source,
    product_suite_sync_config,
)


def owner_record(
    external_suite_id: str = "suite-1",
    namespace_slug: str = "product-a",
    owner_windows_account: str = "hcfange",
) -> ProductSuiteOwnerRecord:
    return ProductSuiteOwnerRecord.create(
        external_suite_id=external_suite_id,
        namespace_slug=namespace_slug,
        owner_windows_account=owner_windows_account,
    )


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


def test_owner_record_constructor_enforces_normalized_fields() -> None:
    record = ProductSuiteOwnerRecord(
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


def test_validate_snapshot_rejects_empty_snapshot() -> None:
    with pytest.raises(ProductSuiteSourceError, match="must not be empty"):
        validate_snapshot([])


@pytest.mark.parametrize(
    "records",
    [
        [
            owner_record("suite-1", "product-a"),
            owner_record("suite-1", "product-b"),
        ],
        [
            owner_record("suite-1", "product-a"),
            owner_record("suite-2", "product-a"),
        ],
    ],
)
def test_validate_snapshot_rejects_duplicate_suite_or_namespace(
    records: list[ProductSuiteOwnerRecord],
) -> None:
    with pytest.raises(ProductSuiteSourceError, match="duplicate"):
        validate_snapshot(records)


def test_validate_snapshot_rejects_non_record_values() -> None:
    with pytest.raises(ProductSuiteSourceError, match="ProductSuiteOwnerRecord"):
        validate_snapshot([{"namespace_slug": "product-a"}])


def test_sync_config_uses_cli_over_environment() -> None:
    config = product_suite_sync_config(
        [
            "--source-module",
            "company.pic_api",
            "--api-url",
            "https://cli.example/api",
            "--timeout-seconds",
            "12",
            "--identity-provider",
            "company-keycloak",
            "--dry-run",
        ],
        environ={
            "SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE": "env.pic_api",
            "SKILLHUB_PRODUCT_SUITE_API_URL": "https://env.example/api",
            "SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS": "45",
            "SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER": "env-keycloak",
        },
    )

    assert config.source_module == "company.pic_api"
    assert config.source.api_url == "https://cli.example/api"
    assert config.source.timeout_seconds == 12
    assert config.identity_provider == "company-keycloak"
    assert config.dry_run is True


def test_sync_config_uses_environment_and_default_provider() -> None:
    config = product_suite_sync_config(
        [],
        environ={
            "SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE": "company.pic_api",
            "SKILLHUB_PRODUCT_SUITE_API_URL": "https://pic.example/api",
        },
    )

    assert config.source.timeout_seconds == 30
    assert config.identity_provider == "keycloak"
    assert config.dry_run is False


@pytest.mark.parametrize(
    ("args", "environ", "error"),
    [
        ([], {}, "source module"),
        (
            [],
            {"SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE": "company.pic_api"},
            "API URL",
        ),
        (
            [
                "--source-module",
                "company.pic_api",
                "--api-url",
                "https://pic.example/api",
                "--timeout-seconds",
                "0",
            ],
            {},
            "timeout",
        ),
        (
            [
                "--source-module",
                "company.pic_api",
                "--api-url",
                "https://pic.example/api",
                "--timeout-seconds",
                "301",
            ],
            {},
            "timeout",
        ),
        (
            [
                "--source-module",
                "company.pic_api",
                "--api-url",
                "https://pic.example/api",
                "--identity-provider",
                " ",
            ],
            {},
            "identity provider",
        ),
    ],
)
def test_sync_config_rejects_invalid_boundaries(
    args: list[str],
    environ: dict[str, str],
    error: str,
) -> None:
    with pytest.raises(ProductSuiteSourceError, match=error):
        product_suite_sync_config(args, environ=environ)


@pytest.mark.anyio
async def test_load_source_calls_internal_async_module() -> None:
    fetcher = load_product_suite_source("tests.support.product_suite_source")

    records = await fetcher(
        ProductSuiteSourceConfig(
            api_url="https://pic.test/api",
            timeout_seconds=30,
        )
    )

    assert records == [owner_record()]


@pytest.mark.parametrize(
    "module_name",
    [
        "tests.support.product_suite_source_missing",
        "tests.support.product_suite_source_sync",
    ],
)
def test_load_source_rejects_missing_or_sync_fetcher(module_name: str) -> None:
    with pytest.raises(ProductSuiteSourceError, match="async fetch_product_suite_owners"):
        load_product_suite_source(module_name)
