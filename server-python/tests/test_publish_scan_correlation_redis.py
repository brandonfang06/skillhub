from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.redis import create_redis_client
from app.core.request_id import current_request_id, request_id_scope
from app.publish.scan_consumer import RedisStreamClient, ScanConsumerRuntime
from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_handoff import RedisScanTaskPublisher
from app.publish.scanner_result import SecurityScanResultInput
from app.publish.side_effects import ScanTaskPayload
from tests.test_publish_scan_worker import FakeConnection

TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


class CorrelationScanner:
    def __init__(self) -> None:
        self.seen_request_ids: list[str | None] = []

    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        self.seen_request_ids.append(current_request_id())
        return SecurityScanResultInput("redis-correlation", "SAFE", 0, "LOW", [], 0.01)


@pytest.mark.skipif(TEST_REDIS_URL is None, reason="requires SKILLHUB_TEST_REDIS_URL")
@pytest.mark.anyio
async def test_real_redis_stream_propagates_and_clears_request_id(tmp_path) -> None:
    settings = replace(get_settings(), redis_mode="single", redis_url=TEST_REDIS_URL or "redis://127.0.0.1:6379/0")
    redis = create_redis_client(settings)
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan:{suffix}"
    group_name = f"skillhub-test-{suffix}"
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    scanner = CorrelationScanner()
    try:
        with request_id_scope("redis-request-1"):
            await RedisScanTaskPublisher(redis, stream_key).publish_scan_task(
                ScanTaskPayload(
                    task_id="task-redis-1",
                    version_id=202,
                    skill_path=None,
                    bundle_key="packages/101/202/bundle.zip",
                    publisher_id="publisher",
                    created_at_millis=1780928116000,
                    metadata={"scannerType": "skill-scanner"},
                )
            )

        runtime = ScanConsumerRuntime(
            RedisStreamClient(redis),
            stream_key=stream_key,
            group_name=group_name,
            consumer_name="correlation-test",
            storage_base_path=str(storage),
            scan_temp_dir=str(tmp_path / "scans"),
        )
        result = await runtime.consume_once(FakeConnection(), scanner, count=1, block_ms=100)

        assert result.processed == 1
        assert result.acknowledged == 1
        assert scanner.seen_request_ids == ["redis-request-1"]
        assert current_request_id() is None

        with request_id_scope("redis-reclaim-1"):
            await RedisScanTaskPublisher(redis, stream_key).publish_scan_task(
                ScanTaskPayload(
                    task_id="task-redis-2",
                    version_id=202,
                    skill_path=None,
                    bundle_key="packages/101/202/bundle.zip",
                    publisher_id="publisher",
                    created_at_millis=1780928117000,
                    metadata={"scannerType": "skill-scanner"},
                )
            )
        await redis.xreadgroup(group_name, "abandoned-consumer", {stream_key: ">"}, count=1, block_ms=100)
        reclaim_scanner = CorrelationScanner()

        reclaimed = await runtime.reclaim_once(
            FakeConnection(),
            reclaim_scanner,
            min_idle_ms=0,
            count=1,
        )

        assert reclaimed.processed == 1
        assert reclaimed.acknowledged == 1
        assert reclaim_scanner.seen_request_ids == ["redis-reclaim-1"]
        assert current_request_id() is None
    finally:
        await redis.delete(stream_key)
        await redis.aclose()
