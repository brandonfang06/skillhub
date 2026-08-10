from __future__ import annotations

import pytest

from app.core.request_id import current_request_id
from app.publish.scan_consumer import (
    MAX_SCAN_RETRY_COUNT,
    RedisStreamClient,
    RedisStreamMessage,
    ScanConsumerRuntime,
    build_retry_stream_fields,
    parse_stream_messages,
)
from app.publish.scan_worker import SecurityScanTask
from app.publish.scanner_result import SecurityScanResultInput
from tests.test_publish_scan_worker import FakeConnection


class FakeRedisStream:
    def __init__(self, messages: list[RedisStreamMessage] | None = None) -> None:
        self.messages = messages or []
        self.acked: list[str] = []
        self.added: list[tuple[str, dict[str, str]]] = []
        self.groups: list[tuple[str, str]] = []
        self.reads: list[tuple[str, str, str, int, int]] = []
        self.reclaims: list[tuple[str, str, int, str, int]] = []

    async def ensure_group(self, stream_key: str, group_name: str) -> None:
        self.groups.append((stream_key, group_name))

    async def read_group(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        *,
        count: int,
        block_ms: int,
    ) -> list[RedisStreamMessage]:
        self.reads.append((stream_key, group_name, consumer_name, count, block_ms))
        return self.messages

    async def reclaim_pending(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        *,
        min_idle_ms: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[RedisStreamMessage]]:
        self.reclaims.append((stream_key, group_name, min_idle_ms, start_id, count))
        return "0-0", self.messages

    async def ack(self, stream_key: str, group_name: str, message_id: str) -> None:
        self.acked.append(message_id)

    async def add(self, stream_key: str, fields: dict[str, str]) -> str:
        self.added.append((stream_key, fields))
        return "retry-1"


class SafeScanner:
    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        return SecurityScanResultInput("scan-1", "SAFE", 0, "LOW", [], 1.0)


class FailingScanner:
    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        raise RuntimeError("scanner unavailable")


class CorrelationScanner:
    def __init__(self) -> None:
        self.seen_request_ids: list[str | None] = []

    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        self.seen_request_ids.append(current_request_id())
        return SecurityScanResultInput("scan-1", "SAFE", 0, "LOW", [], 1.0)


def test_parse_stream_messages_reads_xreadgroup_shape() -> None:
    payload = [["skillhub:scan:requests", [["1780-0", ["taskId", "task-1", "versionId", "202"]]]]]

    messages = parse_stream_messages(payload)

    assert messages == [RedisStreamMessage("1780-0", {"taskId": "task-1", "versionId": "202"})]


def test_parse_stream_messages_reads_redis_py_shape() -> None:
    payload = [("skillhub:scan:requests", [("1780-0", {"taskId": "task-1", "versionId": "202"})])]

    messages = parse_stream_messages(payload)

    assert messages == [RedisStreamMessage("1780-0", {"taskId": "task-1", "versionId": "202"})]


@pytest.mark.anyio
async def test_redis_stream_client_uses_shared_client() -> None:
    class FakeSharedRedis:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        async def xgroup_create(self, *args: object, **kwargs: object) -> None:
            self.calls.append(("xgroup_create", args, kwargs))

        async def xreadgroup(
            self,
            group_name: str,
            consumer_name: str,
            streams: dict[str, str],
            *,
            count: int,
            block_ms: int,
        ) -> object:
            self.calls.append(
                (
                    "xreadgroup",
                    (group_name, consumer_name, streams),
                    {"count": count, "block_ms": block_ms},
                )
            )
            return [("skillhub:scan:requests", [("1780-0", {"taskId": "task-1", "versionId": "202"})])]

        async def xautoclaim(
            self,
            stream_key: str,
            group_name: str,
            consumer_name: str,
            *,
            min_idle_ms: int,
            start_id: str,
            count: int,
        ) -> object:
            self.calls.append(
                (
                    "xautoclaim",
                    (stream_key, group_name, consumer_name),
                    {"min_idle_ms": min_idle_ms, "start_id": start_id, "count": count},
                )
            )
            return ("0-0", [("1780-0", {"taskId": "task-1", "versionId": "202"})])

        async def xack(self, *args: object, **kwargs: object) -> None:
            self.calls.append(("xack", args, kwargs))

        async def xadd(self, *args: object, **kwargs: object) -> str:
            self.calls.append(("xadd", args, kwargs))
            return "1781-0"

    shared = FakeSharedRedis()
    client = RedisStreamClient(shared)

    await client.ensure_group("skillhub:scan:requests", "skillhub-scan-workers")
    messages = await client.read_group(
        "skillhub:scan:requests",
        "skillhub-scan-workers",
        "consumer-1",
        count=10,
        block_ms=2000,
    )
    reclaimed = await client.reclaim_pending(
        "skillhub:scan:requests",
        "skillhub-scan-workers",
        "consumer-1",
        min_idle_ms=120000,
        start_id="0-0",
        count=20,
    )
    await client.ack("skillhub:scan:requests", "skillhub-scan-workers", "1780-0")
    added = await client.add("skillhub:scan:requests", {"taskId": "task-2"})

    assert messages == [RedisStreamMessage("1780-0", {"taskId": "task-1", "versionId": "202"})]
    assert reclaimed == ("0-0", [RedisStreamMessage("1780-0", {"taskId": "task-1", "versionId": "202"})])
    assert added == "1781-0"
    assert [call[0] for call in shared.calls] == ["xgroup_create", "xreadgroup", "xautoclaim", "xack", "xadd"]
    assert shared.calls[1][2] == {"count": 10, "block_ms": 2000}
    assert shared.calls[2][2] == {"min_idle_ms": 120000, "start_id": "0-0", "count": 20}


def test_build_retry_stream_fields_preserves_java_task_shape() -> None:
    task = SecurityScanTask(
        task_id="task-1",
        version_id=202,
        skill_path=None,
        bundle_key="packages/101/202/bundle.zip",
        scanner_type="skill-scanner",
        retry_count=1,
    )

    assert build_retry_stream_fields(task, retry_count=2, created_at_millis=1780969000000) == {
        "taskId": "task-1",
        "versionId": "202",
        "bundleKey": "packages/101/202/bundle.zip",
        "publisherId": "",
        "createdAtMillis": "1780969000000",
        "retryCount": "2",
        "scannerType": "skill-scanner",
    }


@pytest.mark.anyio
async def test_consume_once_creates_group_processes_message_and_acks(tmp_path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    redis = FakeRedisStream(
        [
            RedisStreamMessage(
                "1780-0",
                {
                    "taskId": "task-1",
                    "versionId": "202",
                    "bundleKey": "packages/101/202/bundle.zip",
                    "scannerType": "skill-scanner",
                },
            )
        ]
    )
    runtime = ScanConsumerRuntime(
        redis,
        stream_key="skillhub:scan:requests",
        group_name="skillhub-scan-workers",
        consumer_name="scanner-test",
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
    )

    result = await runtime.consume_once(FakeConnection(), SafeScanner())

    assert result.processed == 1
    assert result.acknowledged == 1
    assert result.retried == 0
    assert redis.groups == [("skillhub:scan:requests", "skillhub-scan-workers")]
    assert redis.acked == ["1780-0"]


@pytest.mark.anyio
async def test_consume_once_scopes_and_clears_propagated_request_id(tmp_path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    scanner = CorrelationScanner()
    redis = FakeRedisStream(
        [
            RedisStreamMessage(
                "1780-0",
                {
                    "taskId": "task-1",
                    "versionId": "202",
                    "bundleKey": "packages/101/202/bundle.zip",
                    "scannerType": "skill-scanner",
                    "skillhub.request_id": "request-from-http",
                },
            )
        ]
    )
    runtime = ScanConsumerRuntime(
        redis,
        stream_key="skillhub:scan:requests",
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
    )

    await runtime.consume_once(FakeConnection(), scanner)

    assert scanner.seen_request_ids == ["request-from-http"]
    assert current_request_id() is None


@pytest.mark.anyio
async def test_consume_once_retries_failure_without_marking_failed_before_max_retry(tmp_path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    redis = FakeRedisStream(
        [
            RedisStreamMessage(
                "1780-0",
                {
                    "taskId": "task-1",
                    "versionId": "202",
                    "bundleKey": "packages/101/202/bundle.zip",
                    "scannerType": "skill-scanner",
                    "retryCount": "2",
                    "skillhub.request_id": "request-for-retry",
                },
            )
        ]
    )
    connection = FakeConnection()
    runtime = ScanConsumerRuntime(
        redis,
        stream_key="skillhub:scan:requests",
        group_name="skillhub-scan-workers",
        consumer_name="scanner-test",
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
        clock_millis=lambda: 1780969000000,
    )

    result = await runtime.consume_once(connection, FailingScanner())

    assert result.processed == 1
    assert result.retried == 1
    assert result.failed == 0
    assert redis.acked == ["1780-0"]
    assert redis.added == [
        (
            "skillhub:scan:requests",
            {
                "taskId": "task-1",
                "versionId": "202",
                "bundleKey": "packages/101/202/bundle.zip",
                "publisherId": "",
                "createdAtMillis": "1780969000000",
                "retryCount": "3",
                "scannerType": "skill-scanner",
                "skillhub.request_id": "request-for-retry",
            },
        )
    ]
    assert current_request_id() is None
    assert not any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_consume_once_marks_failed_at_max_retry(tmp_path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    redis = FakeRedisStream(
        [
            RedisStreamMessage(
                "1780-0",
                {
                    "taskId": "task-1",
                    "versionId": "202",
                    "bundleKey": "packages/101/202/bundle.zip",
                    "scannerType": "skill-scanner",
                    "retryCount": str(MAX_SCAN_RETRY_COUNT),
                },
            )
        ]
    )
    connection = FakeConnection()
    runtime = ScanConsumerRuntime(
        redis,
        stream_key="skillhub:scan:requests",
        group_name="skillhub-scan-workers",
        consumer_name="scanner-test",
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
    )

    result = await runtime.consume_once(connection, FailingScanner())

    assert result.processed == 1
    assert result.retried == 0
    assert result.failed == 1
    assert redis.acked == ["1780-0"]
    assert any("UPDATE skill_version" in statement and "SCAN_FAILED" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_reclaim_once_processes_pending_messages(tmp_path) -> None:
    storage = tmp_path / "storage"
    bundle = storage / "packages" / "101" / "202" / "bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"zip-bytes")
    redis = FakeRedisStream(
        [
            RedisStreamMessage(
                "1780-0",
                {
                    "taskId": "task-1",
                    "versionId": "202",
                    "bundleKey": "packages/101/202/bundle.zip",
                    "scannerType": "skill-scanner",
                },
            )
        ]
    )
    runtime = ScanConsumerRuntime(
        redis,
        stream_key="skillhub:scan:requests",
        group_name="skillhub-scan-workers",
        consumer_name="scanner-test",
        storage_base_path=str(storage),
        scan_temp_dir=str(tmp_path / "scans"),
    )

    result = await runtime.reclaim_once(FakeConnection(), SafeScanner(), min_idle_ms=120000, count=20)

    assert result.processed == 1
    assert redis.reclaims == [("skillhub:scan:requests", "skillhub-scan-workers", 120000, "0-0", 20)]
    assert redis.acked == ["1780-0"]
