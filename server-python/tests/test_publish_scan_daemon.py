from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.config import get_settings
from app.publish.scan_daemon import ScanConsumerDaemon, create_scan_consumer_daemon
from app.publish.scan_consumer import ScanConsumerResult


class FakeEngine:
    def begin(self) -> "FakeBegin":
        return FakeBegin()


class FakeBegin:
    async def __aenter__(self) -> "FakeConnection":
        return FakeConnection()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnection:
    pass


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.consume_calls = 0
        self.reclaim_calls = 0

    async def ensure_group(self) -> None:
        self.calls.append("ensure_group")

    async def consume_once(self, connection: Any, scanner: object, *, count: int, block_ms: int) -> ScanConsumerResult:
        self.calls.append("consume_once")
        self.consume_calls += 1
        return ScanConsumerResult(processed=1, acknowledged=1)

    async def reclaim_once(
        self,
        connection: Any,
        scanner: object,
        *,
        min_idle_ms: int,
        count: int,
    ) -> ScanConsumerResult:
        self.calls.append("reclaim_once")
        self.reclaim_calls += 1
        return ScanConsumerResult()


class FakeScanner:
    pass


def test_scan_consumer_settings_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "SKILLHUB_SCAN_CONSUMER_ENABLED",
        "SKILLHUB_SCAN_CONSUMER_GROUP_NAME",
        "SKILLHUB_SCAN_CONSUMER_NAME",
        "SKILLHUB_SCAN_CONSUMER_READ_COUNT",
        "SKILLHUB_SCAN_CONSUMER_BLOCK_MS",
        "SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS",
        "SKILLHUB_SCAN_CONSUMER_RECLAIM_COUNT",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.scan_consumer_enabled is False
    assert settings.scan_consumer_group_name == "skillhub-scan-workers"
    assert settings.scan_consumer_name.startswith("scanner-python-")
    assert settings.scan_consumer_read_count == 10
    assert settings.scan_consumer_block_ms == 2000
    assert settings.scan_consumer_reclaim_min_idle_ms == 120000
    assert settings.scan_consumer_reclaim_count == 20


def test_scan_consumer_settings_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_GROUP_NAME", "group-1")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_NAME", "consumer-1")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_READ_COUNT", "3")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_BLOCK_MS", "250")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS", "5000")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_RECLAIM_COUNT", "7")

    settings = get_settings()

    assert settings.scan_consumer_enabled is True
    assert settings.scan_consumer_group_name == "group-1"
    assert settings.scan_consumer_name == "consumer-1"
    assert settings.scan_consumer_read_count == 3
    assert settings.scan_consumer_block_ms == 250
    assert settings.scan_consumer_reclaim_min_idle_ms == 5000
    assert settings.scan_consumer_reclaim_count == 7


@pytest.mark.anyio
async def test_daemon_loop_consumes_and_reclaims_until_stopped() -> None:
    runtime = FakeRuntime()
    daemon = ScanConsumerDaemon(
        engine=FakeEngine(),
        runtime=runtime,
        scanner=FakeScanner(),
        read_count=2,
        block_ms=10,
        reclaim_min_idle_ms=5000,
        reclaim_count=4,
        error_sleep_seconds=0.01,
    )

    task = asyncio.create_task(daemon.run())
    await asyncio.sleep(0.01)
    daemon.stop()
    await task

    assert runtime.consume_calls >= 1
    assert runtime.reclaim_calls >= 1


@pytest.mark.anyio
async def test_daemon_loop_ensures_consumer_group_before_reading() -> None:
    runtime = FakeRuntime()
    daemon = ScanConsumerDaemon(
        engine=FakeEngine(),
        runtime=runtime,
        scanner=FakeScanner(),
        read_count=2,
        block_ms=10,
        reclaim_min_idle_ms=5000,
        reclaim_count=4,
        error_sleep_seconds=0.01,
    )

    task = asyncio.create_task(daemon.run())
    await asyncio.sleep(0.01)
    daemon.stop()
    await task

    assert runtime.calls[:3] == ["ensure_group", "consume_once", "reclaim_once"]


@pytest.mark.anyio
async def test_daemon_start_and_shutdown_manage_background_task() -> None:
    runtime = FakeRuntime()
    daemon = ScanConsumerDaemon(
        engine=FakeEngine(),
        runtime=runtime,
        scanner=FakeScanner(),
        read_count=2,
        block_ms=10,
        reclaim_min_idle_ms=5000,
        reclaim_count=4,
        error_sleep_seconds=0.01,
    )

    daemon.start()
    assert daemon.task is not None
    await asyncio.sleep(0.01)
    await daemon.shutdown()

    assert daemon.task is None
    assert runtime.consume_calls >= 1


def test_create_scan_consumer_daemon_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLHUB_SCAN_CONSUMER_ENABLED", raising=False)
    settings = get_settings()

    assert create_scan_consumer_daemon(settings, FakeEngine()) is None


def test_create_scan_consumer_daemon_uses_settings_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_MODE", "upload")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_BEHAVIORAL", "false")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_LLM", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_META", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_AI_DEFENSE", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_AI_DEFENSE_API_KEY", "aidefense-secret")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_VIRUSTOTAL", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_TRIGGER", "true")
    settings = get_settings()

    daemon = create_scan_consumer_daemon(settings, FakeEngine())

    assert daemon is not None
    assert daemon.read_count == settings.scan_consumer_read_count
    assert daemon.block_ms == settings.scan_consumer_block_ms
    assert daemon.scanner.options.use_behavioral is False
    assert daemon.scanner.options.use_llm is True
    assert daemon.scanner.options.llm_provider == "openai"
    assert daemon.scanner.options.enable_meta is True
    assert daemon.scanner.options.use_aidefense is True
    assert daemon.scanner.options.aidefense_api_key == "aidefense-secret"
    assert daemon.scanner.options.use_virustotal is True
    assert daemon.scanner.options.use_trigger is True
