from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.integrations.product_suite import cli
from app.integrations.product_suite.cli import (
    ProductSuiteCommandResult,
    run_product_suite_sync,
)
from app.integrations.product_suite.contracts import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
    ProductSuiteSyncConfig,
    ProductSuiteSyncIssue,
    ProductSuiteSyncSummary,
)


def sync_config() -> ProductSuiteSyncConfig:
    return ProductSuiteSyncConfig(
        source_module="company.pic_api",
        source=ProductSuiteSourceConfig(
            api_url="https://pic.example/api",
            timeout_seconds=30,
        ),
        identity_provider="keycloak",
        dry_run=False,
    )


def owner_record() -> ProductSuiteOwnerRecord:
    return ProductSuiteOwnerRecord.create(
        external_suite_id="suite-a",
        namespace_slug="product-a",
        owner_windows_account="hcfange",
    )


async def successful_source(
    config: ProductSuiteSourceConfig,
) -> list[ProductSuiteOwnerRecord]:
    assert config.api_url == "https://pic.example/api"
    return [owner_record()]


class DisposableEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.anyio
async def test_run_sync_outputs_summary_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = DisposableEngine()
    summary = ProductSuiteSyncSummary(
        suites_fetched=1,
        namespaces_resolved=1,
        waiting_for_login=1,
    )

    async def fake_reconcile(*args: Any, **kwargs: Any) -> ProductSuiteSyncSummary:
        return summary

    monkeypatch.setattr(cli, "reconcile_product_suite_admins", fake_reconcile)

    result = await run_product_suite_sync(
        config=sync_config(),
        source_loader=lambda _: successful_source,
        engine_factory=lambda _: engine,
    )

    assert result.exit_code == 0
    assert result.to_payload()["summary"]["waitingForLogin"] == 1
    assert engine.disposed is True


@pytest.mark.parametrize(
    "summary",
    [
        ProductSuiteSyncSummary(blocked=1),
        ProductSuiteSyncSummary(identity_conflicts=1),
    ],
)
@pytest.mark.anyio
async def test_run_sync_returns_one_for_operator_attention(
    monkeypatch: pytest.MonkeyPatch,
    summary: ProductSuiteSyncSummary,
) -> None:
    engine = DisposableEngine()

    async def fake_reconcile(*args: Any, **kwargs: Any) -> ProductSuiteSyncSummary:
        return summary

    monkeypatch.setattr(cli, "reconcile_product_suite_admins", fake_reconcile)

    result = await run_product_suite_sync(
        config=sync_config(),
        source_loader=lambda _: successful_source,
        engine_factory=lambda _: engine,
    )

    assert result.exit_code == 1
    assert result.to_payload()["status"] == "attention"
    assert engine.disposed is True


@pytest.mark.anyio
async def test_run_sync_returns_two_without_creating_engine_when_source_fails() -> None:
    factory_calls = 0

    async def failing_source(
        config: ProductSuiteSourceConfig,
    ) -> list[ProductSuiteOwnerRecord]:
        raise RuntimeError("PIC API unavailable")

    def engine_factory(settings: object) -> object:
        nonlocal factory_calls
        factory_calls += 1
        return object()

    result = await run_product_suite_sync(
        config=sync_config(),
        source_loader=lambda _: failing_source,
        engine_factory=engine_factory,
    )

    assert result.exit_code == 2
    assert result.to_payload()["status"] == "fatal"
    assert "PIC API unavailable" in result.to_payload()["error"]["detail"]
    assert factory_calls == 0


@pytest.mark.anyio
async def test_run_sync_enforces_source_timeout_before_creating_engine() -> None:
    factory_calls = 0
    config = sync_config()
    config = ProductSuiteSyncConfig(
        source_module=config.source_module,
        source=ProductSuiteSourceConfig(
            api_url=config.source.api_url,
            timeout_seconds=0.001,
        ),
        identity_provider=config.identity_provider,
        dry_run=config.dry_run,
    )

    async def slow_source(
        source_config: ProductSuiteSourceConfig,
    ) -> list[ProductSuiteOwnerRecord]:
        await asyncio.sleep(0.02)
        return [owner_record()]

    def engine_factory(settings: object) -> object:
        nonlocal factory_calls
        factory_calls += 1
        return object()

    result = await run_product_suite_sync(
        config=config,
        source_loader=lambda _: slow_source,
        engine_factory=engine_factory,
    )

    assert result.exit_code == 2
    assert "timed out" in result.error_detail
    assert factory_calls == 0


@pytest.mark.anyio
async def test_run_sync_returns_two_and_disposes_engine_when_database_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = DisposableEngine()

    async def failing_reconcile(*args: Any, **kwargs: Any) -> ProductSuiteSyncSummary:
        raise RuntimeError("database write failed")

    monkeypatch.setattr(cli, "reconcile_product_suite_admins", failing_reconcile)

    result = await run_product_suite_sync(
        config=sync_config(),
        source_loader=lambda _: successful_source,
        engine_factory=lambda _: engine,
    )

    assert result.exit_code == 2
    assert "database write failed" in result.error_detail
    assert engine.disposed is True


def test_command_result_serializes_camel_case_summary_and_issues() -> None:
    result = ProductSuiteCommandResult.from_summary(
        ProductSuiteSyncSummary(
            suites_fetched=2,
            administrators_added=1,
            waiting_for_login=1,
            blocked=1,
            issues=[
                ProductSuiteSyncIssue(
                    external_suite_id="suite-b",
                    namespace_slug="product-b",
                    owner_windows_account="alice",
                    code="NAMESPACE_NOT_FOUND",
                    detail="namespace does not exist",
                )
            ],
            dry_run=True,
        )
    )

    payload = result.to_payload()

    assert payload == {
        "status": "attention",
        "exitCode": 1,
        "summary": {
            "suitesFetched": 2,
            "namespacesResolved": 0,
            "administratorsAdded": 1,
            "membersPromoted": 0,
            "membershipsUnchanged": 0,
            "waitingForLogin": 1,
            "blocked": 1,
            "identityConflicts": 0,
            "issues": [
                {
                    "externalSuiteId": "suite-b",
                    "namespaceSlug": "product-b",
                    "ownerWindowsAccount": "alice",
                    "code": "NAMESPACE_NOT_FOUND",
                    "detail": "namespace does not exist",
                }
            ],
            "dryRun": True,
        },
    }


def test_main_writes_exactly_one_json_object(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(
        *,
        config: ProductSuiteSyncConfig,
        source_loader: object = None,
        engine_factory: object = None,
    ) -> ProductSuiteCommandResult:
        return ProductSuiteCommandResult.from_summary(
            ProductSuiteSyncSummary(suites_fetched=1)
        )

    monkeypatch.setattr(cli, "run_product_suite_sync", fake_run)

    exit_code = cli.main(
        [
            "--source-module",
            "company.pic_api",
            "--api-url",
            "https://pic.example/api",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert len(captured.out.strip().splitlines()) == 1
    assert json.loads(captured.out)["status"] == "ok"
    assert captured.err == ""


def test_main_maps_configuration_failure_to_fatal_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.out)["status"] == "fatal"
    assert "source module" in captured.err
    assert "Traceback" not in captured.err


def test_main_maps_invalid_cli_value_to_fatal_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "--source-module",
            "company.pic_api",
            "--api-url",
            "https://pic.example/api",
            "--timeout-seconds",
            "invalid",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert len(captured.out.strip().splitlines()) == 1
    assert json.loads(captured.out)["status"] == "fatal"
    assert "timeout-seconds" in captured.err
    assert "Traceback" not in captured.err
