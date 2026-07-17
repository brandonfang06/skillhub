from __future__ import annotations

from collections.abc import Sequence

from app.integrations.product_suite.contracts import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
)


async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    assert config.api_url == "https://pic.test/api"
    return [
        ProductSuiteOwnerRecord.create(
            external_suite_id="suite-1",
            namespace_slug="product-a",
            owner_windows_account="hcfange",
        )
    ]
