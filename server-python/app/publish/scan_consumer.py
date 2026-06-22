from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from app.object_storage import ObjectStorage
from app.publish.scan_worker import (
    ScannerClient,
    SecurityScanTask,
    parse_scan_task_fields,
    process_scan_task,
)


MAX_SCAN_RETRY_COUNT = 3
DEFAULT_SCAN_GROUP_NAME = "skillhub-scan-workers"
DEFAULT_SCAN_CONSUMER_NAME = "scanner-python"
DEFAULT_READ_COUNT = 10
DEFAULT_BLOCK_MS = 2000

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class RedisStreamMessage:
    message_id: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ScanConsumerResult:
    processed: int = 0
    acknowledged: int = 0
    retried: int = 0
    failed: int = 0
    invalid: int = 0

    def plus(self, other: "ScanConsumerResult") -> "ScanConsumerResult":
        return ScanConsumerResult(
            processed=self.processed + other.processed,
            acknowledged=self.acknowledged + other.acknowledged,
            retried=self.retried + other.retried,
            failed=self.failed + other.failed,
            invalid=self.invalid + other.invalid,
        )


class RedisStream(Protocol):
    async def ensure_group(self, stream_key: str, group_name: str) -> None:
        pass

    async def read_group(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        *,
        count: int,
        block_ms: int,
    ) -> list[RedisStreamMessage]:
        pass

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
        pass

    async def ack(self, stream_key: str, group_name: str, message_id: str) -> None:
        pass

    async def add(self, stream_key: str, fields: dict[str, str]) -> str:
        pass


def parse_stream_messages(payload: Any) -> list[RedisStreamMessage]:
    if payload is None:
        return []

    messages: list[RedisStreamMessage] = []
    for stream_entry in payload:
        if not isinstance(stream_entry, (list, tuple)) or len(stream_entry) != 2:
            continue
        raw_messages = stream_entry[1]
        if not isinstance(raw_messages, (list, tuple)):
            continue
        for raw_message in raw_messages:
            if not isinstance(raw_message, (list, tuple)) or len(raw_message) != 2:
                continue
            message_id = str(raw_message[0])
            raw_fields = raw_message[1]
            fields: dict[str, str] = {}
            if isinstance(raw_fields, dict):
                for key, value in raw_fields.items():
                    fields[str(key)] = str(value)
            elif isinstance(raw_fields, (list, tuple)):
                for index in range(0, len(raw_fields) - 1, 2):
                    fields[str(raw_fields[index])] = str(raw_fields[index + 1])
            else:
                continue
            messages.append(RedisStreamMessage(message_id, fields))
    return messages


def build_retry_stream_fields(
    task: SecurityScanTask,
    *,
    retry_count: int,
    created_at_millis: int | None = None,
) -> dict[str, str]:
    fields = {
        "taskId": task.task_id or "",
        "versionId": str(task.version_id),
        "publisherId": "",
        "createdAtMillis": str(created_at_millis if created_at_millis is not None else int(time.time() * 1000)),
        "retryCount": str(retry_count),
        "scannerType": task.scanner_type,
    }
    if task.skill_path:
        fields["skillPath"] = task.skill_path
    if task.bundle_key:
        fields["bundleKey"] = task.bundle_key
    return fields


class ScanConsumerRuntime:
    def __init__(
        self,
        redis: RedisStream,
        *,
        stream_key: str,
        group_name: str = DEFAULT_SCAN_GROUP_NAME,
        consumer_name: str = DEFAULT_SCAN_CONSUMER_NAME,
        storage_base_path: str,
        scan_temp_dir: str,
        storage: ObjectStorage | None = None,
        clock_millis: Callable[[], int] | None = None,
    ) -> None:
        self.redis = redis
        self.stream_key = stream_key
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.storage_base_path = storage_base_path
        self.scan_temp_dir = scan_temp_dir
        self.storage = storage
        self.clock_millis = clock_millis or (lambda: int(time.time() * 1000))
        self._group_ready = False

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        await self.redis.ensure_group(self.stream_key, self.group_name)
        self._group_ready = True

    async def consume_once(
        self,
        connection: Any,
        scanner: ScannerClient,
        *,
        count: int = DEFAULT_READ_COUNT,
        block_ms: int = DEFAULT_BLOCK_MS,
    ) -> ScanConsumerResult:
        await self.ensure_group()
        messages = await self.redis.read_group(
            self.stream_key,
            self.group_name,
            self.consumer_name,
            count=count,
            block_ms=block_ms,
        )
        return await self._process_messages(connection, scanner, messages)

    async def reclaim_once(
        self,
        connection: Any,
        scanner: ScannerClient,
        *,
        min_idle_ms: int,
        start_id: str = "0-0",
        count: int = 20,
    ) -> ScanConsumerResult:
        await self.ensure_group()
        _, messages = await self.redis.reclaim_pending(
            self.stream_key,
            self.group_name,
            self.consumer_name,
            min_idle_ms=min_idle_ms,
            start_id=start_id,
            count=count,
        )
        return await self._process_messages(connection, scanner, messages)

    async def _process_messages(
        self,
        connection: Any,
        scanner: ScannerClient,
        messages: list[RedisStreamMessage],
    ) -> ScanConsumerResult:
        result = ScanConsumerResult()
        for message in messages:
            result = result.plus(await self._process_message(connection, scanner, message))
        return result

    async def _process_message(
        self,
        connection: Any,
        scanner: ScannerClient,
        message: RedisStreamMessage,
    ) -> ScanConsumerResult:
        task = parse_scan_task_fields(message.fields)
        if task is None:
            logger.warning("Ignoring invalid scan task message: id=%s fields=%s", message.message_id, message.fields)
            await self.redis.ack(self.stream_key, self.group_name, message.message_id)
            return ScanConsumerResult(acknowledged=1, invalid=1)

        try:
            logger.info(
                "Processing scan task: message_id=%s version_id=%s retry_count=%s",
                message.message_id,
                task.version_id,
                task.retry_count,
            )
            await process_scan_task(
                connection,
                task,
                scanner,
                storage_base_path=self.storage_base_path,
                scan_temp_dir=self.scan_temp_dir,
                storage=self.storage,
                mark_failed_on_error=task.retry_count >= MAX_SCAN_RETRY_COUNT,
            )
            await self.redis.ack(self.stream_key, self.group_name, message.message_id)
            return ScanConsumerResult(processed=1, acknowledged=1)
        except Exception as exc:
            if task.retry_count < MAX_SCAN_RETRY_COUNT:
                logger.warning(
                    "Scan task failed; retrying: message_id=%s version_id=%s retry_count=%s error=%s",
                    message.message_id,
                    task.version_id,
                    task.retry_count,
                    exc,
                )
                await self.redis.add(
                    self.stream_key,
                    build_retry_stream_fields(task, retry_count=task.retry_count + 1, created_at_millis=self.clock_millis()),
                )
                await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                return ScanConsumerResult(processed=1, acknowledged=1, retried=1)

            logger.exception(
                "Scan task failed permanently: message_id=%s version_id=%s retry_count=%s",
                message.message_id,
                task.version_id,
                task.retry_count,
            )
            await self.redis.ack(self.stream_key, self.group_name, message.message_id)
            return ScanConsumerResult(processed=1, acknowledged=1, failed=1)


class RedisStreamClient:
    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    async def ensure_group(self, stream_key: str, group_name: str) -> None:
        try:
            await self.redis_client.xgroup_create(stream_key, group_name, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_group(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        *,
        count: int,
        block_ms: int,
    ) -> list[RedisStreamMessage]:
        payload = await self.redis_client.xreadgroup(
            group_name,
            consumer_name,
            {stream_key: ">"},
            count=count,
            block_ms=block_ms,
        )
        return parse_stream_messages(payload)

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
        payload = await self.redis_client.xautoclaim(
            stream_key,
            group_name,
            consumer_name,
            min_idle_ms=min_idle_ms,
            start_id=start_id,
            count=count,
        )
        if not isinstance(payload, (list, tuple)) or len(payload) < 2:
            return "0-0", []
        return str(payload[0]), _parse_autoclaim_messages(payload[1])

    async def ack(self, stream_key: str, group_name: str, message_id: str) -> None:
        await self.redis_client.xack(stream_key, group_name, message_id)

    async def add(self, stream_key: str, fields: dict[str, str]) -> str:
        return await self.redis_client.xadd(stream_key, fields)


def _parse_autoclaim_messages(payload: Any) -> list[RedisStreamMessage]:
    if not isinstance(payload, (list, tuple)):
        return []
    return parse_stream_messages([["", payload]])
