from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import Settings
from app.object_storage import object_storage_for_settings
from app.publish.scan_consumer import RedisStreamClient, ScanConsumerRuntime
from app.publish.scanner_client import ScannerHttpClient, ScanOptions

logger = logging.getLogger("uvicorn.error")


class ScanConsumerDaemon:
    def __init__(
        self,
        *,
        engine: Any,
        runtime: ScanConsumerRuntime,
        scanner: Any,
        read_count: int,
        block_ms: int,
        reclaim_min_idle_ms: int,
        reclaim_count: int,
        error_sleep_seconds: float = 1.0,
    ) -> None:
        self.engine = engine
        self.runtime = runtime
        self.scanner = scanner
        self.read_count = read_count
        self.block_ms = block_ms
        self.reclaim_min_idle_ms = reclaim_min_idle_ms
        self.reclaim_count = reclaim_count
        self.error_sleep_seconds = error_sleep_seconds
        self._running = False
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self.task is not None:
            return
        self._running = True
        logger.info("Starting scan consumer daemon")
        self.task = asyncio.create_task(self.run())

    def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        self.stop()
        if self.task is None:
            return
        logger.info("Stopping scan consumer daemon")
        task = self.task
        self.task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.runtime.ensure_group()
                await self.runtime.consume_once(
                    self.engine,
                    self.scanner,
                    count=self.read_count,
                    block_ms=self.block_ms,
                )
                await self.runtime.reclaim_once(
                    self.engine,
                    self.scanner,
                    min_idle_ms=self.reclaim_min_idle_ms,
                    count=self.reclaim_count,
                )
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scan consumer daemon iteration failed")
                await asyncio.sleep(self.error_sleep_seconds)


def create_scan_consumer_daemon(settings: Settings, engine: Any, redis_client: Any) -> ScanConsumerDaemon | None:
    if not settings.scan_consumer_enabled:
        logger.info("Scan consumer daemon disabled")
        return None

    logger.info(
        "Creating scan consumer daemon: stream=%s group=%s consumer=%s scanner=%s",
        settings.scan_stream_key,
        settings.scan_consumer_group_name,
        settings.scan_consumer_name,
        settings.scanner_base_url,
    )
    runtime = ScanConsumerRuntime(
        RedisStreamClient(redis_client),
        stream_key=settings.scan_stream_key,
        group_name=settings.scan_consumer_group_name,
        consumer_name=settings.scan_consumer_name,
        storage_base_path=settings.storage_base_path,
        scan_temp_dir=str(settings.storage_base_path.rstrip("/\\") + "-scan-temp"),
        storage=object_storage_for_settings(settings),
    )
    scanner = ScannerHttpClient(
        base_url=settings.scanner_base_url,
        mode=settings.security_scanner_mode,
        scan_path=settings.scanner_scan_path,
        connect_timeout_ms=settings.scanner_connect_timeout_ms,
        read_timeout_ms=settings.scanner_read_timeout_ms,
        options=ScanOptions(
            use_behavioral=settings.scanner_use_behavioral,
            use_llm=settings.scanner_use_llm,
            llm_provider=settings.scanner_llm_provider,
            enable_meta=settings.scanner_enable_meta,
            use_aidefense=settings.scanner_use_aidefense,
            aidefense_api_key=settings.scanner_aidefense_api_key,
            use_virustotal=settings.scanner_use_virustotal,
            use_trigger=settings.scanner_use_trigger,
        ),
    )
    return ScanConsumerDaemon(
        engine=engine,
        runtime=runtime,
        scanner=scanner,
        read_count=settings.scan_consumer_read_count,
        block_ms=settings.scan_consumer_block_ms,
        reclaim_min_idle_ms=settings.scan_consumer_reclaim_min_idle_ms,
        reclaim_count=settings.scan_consumer_reclaim_count,
    )
