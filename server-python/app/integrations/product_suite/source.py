from __future__ import annotations

import argparse
from collections.abc import Awaitable, Callable, Mapping, Sequence
import importlib
import inspect
import os

from app.integrations.product_suite.contracts import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
    ProductSuiteSourceError,
    ProductSuiteSyncConfig,
)


ProductSuiteSource = Callable[
    [ProductSuiteSourceConfig],
    Awaitable[Sequence[ProductSuiteOwnerRecord]],
]


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize product suite owners as namespace administrators."
    )
    parser.add_argument("--source-module")
    parser.add_argument("--api-url")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--identity-provider")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _configured_value(cli_value: str | None, environ_value: str | None) -> str:
    if cli_value is not None:
        return cli_value
    return environ_value or ""


def product_suite_sync_config(
    args: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
) -> ProductSuiteSyncConfig:
    parsed = _argument_parser().parse_args(args)
    values = os.environ if environ is None else environ

    source_module = _configured_value(
        parsed.source_module,
        values.get("SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE"),
    ).strip()
    if not source_module:
        raise ProductSuiteSourceError("source module must not be empty")

    api_url = _configured_value(
        parsed.api_url,
        values.get("SKILLHUB_PRODUCT_SUITE_API_URL"),
    ).strip()
    if not api_url:
        raise ProductSuiteSourceError("API URL must not be empty")

    configured_timeout = parsed.timeout_seconds
    if configured_timeout is None:
        raw_timeout = values.get(
            "SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS",
            "30",
        )
        try:
            configured_timeout = float(raw_timeout)
        except ValueError as exc:
            raise ProductSuiteSourceError(
                "timeout must be a number between 0 and 300 seconds"
            ) from exc
    if configured_timeout <= 0 or configured_timeout > 300:
        raise ProductSuiteSourceError(
            "timeout must be greater than 0 and no greater than 300 seconds"
        )

    identity_provider = _configured_value(
        parsed.identity_provider,
        values.get(
            "SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER",
            "keycloak",
        ),
    ).strip()
    if not identity_provider:
        raise ProductSuiteSourceError("identity provider must not be empty")

    return ProductSuiteSyncConfig(
        source_module=source_module,
        source=ProductSuiteSourceConfig(
            api_url=api_url,
            timeout_seconds=configured_timeout,
        ),
        identity_provider=identity_provider,
        dry_run=bool(parsed.dry_run),
    )


def load_product_suite_source(module_name: str) -> ProductSuiteSource:
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise ProductSuiteSourceError(
            f"{module_name} must define async fetch_product_suite_owners(config)"
        ) from exc

    fetcher = getattr(module, "fetch_product_suite_owners", None)
    if not callable(fetcher) or not inspect.iscoroutinefunction(fetcher):
        raise ProductSuiteSourceError(
            f"{module_name} must define async fetch_product_suite_owners(config)"
        )
    return fetcher
