from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.request_id import (
    MESSAGE_REQUEST_ID_FIELD,
    current_request_id,
    is_valid_request_id,
    request_id_scope,
)
from app.object_storage import ObjectStorage
from app.publish.scan_worker import (
    ScannerClient,
    ScanTaskAlreadyFinalized,
    ScanTaskLeaseUnavailable,
    ScanTaskNotReady,
    SecurityScanTask,
    acquire_scan_task_lease,
    mark_scan_task_failed,
    parse_scan_task_fields,
    process_scan_task,
)

MAX_SCAN_RETRY_COUNT = 3
MAX_SCAN_NOT_READY_REQUEUE_COUNT = 30
MAX_SCAN_NOT_READY_AGE_MS = 120000
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

    def plus(self, other: ScanConsumerResult) -> ScanConsumerResult:
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
    visibility_retry_count: int | None = None,
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
    if visibility_retry_count is not None:
        fields["visibilityRetryCount"] = str(visibility_retry_count)
    request_id = current_request_id()
    if is_valid_request_id(request_id):
        fields[MESSAGE_REQUEST_ID_FIELD] = request_id
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
        max_not_ready_requeue_count: int = MAX_SCAN_NOT_READY_REQUEUE_COUNT,
        max_not_ready_age_ms: int = MAX_SCAN_NOT_READY_AGE_MS,
    ) -> None:
        self.redis = redis
        self.stream_key = stream_key
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.storage_base_path = storage_base_path
        self.scan_temp_dir = scan_temp_dir
        self.storage = storage
        self.clock_millis = clock_millis or (lambda: int(time.time() * 1000))
        self.max_not_ready_requeue_count = max_not_ready_requeue_count
        self.max_not_ready_age_ms = max_not_ready_age_ms
        self._group_ready = False
        self._reclaim_start_id = "0-0"

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        await self.redis.ensure_group(self.stream_key, self.group_name)
        self._group_ready = True

    async def consume_once(
        self,
        engine: Any,
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
        return await self._process_messages(engine, scanner, messages)

    async def reclaim_once(
        self,
        engine: Any,
        scanner: ScannerClient,
        *,
        min_idle_ms: int,
        start_id: str | None = None,
        count: int = 20,
    ) -> ScanConsumerResult:
        await self.ensure_group()
        next_start_id, messages = await self.redis.reclaim_pending(
            self.stream_key,
            self.group_name,
            self.consumer_name,
            min_idle_ms=min_idle_ms,
            start_id=start_id or self._reclaim_start_id,
            count=count,
        )
        self._reclaim_start_id = next_start_id
        return await self._process_messages(engine, scanner, messages)

    async def _process_messages(
        self,
        engine: Any,
        scanner: ScannerClient,
        messages: list[RedisStreamMessage],
    ) -> ScanConsumerResult:
        result = ScanConsumerResult()
        for message in messages:
            result = result.plus(await self._process_message(engine, scanner, message))
        return result

    async def _process_message(
        self,
        engine: Any,
        scanner: ScannerClient,
        message: RedisStreamMessage,
    ) -> ScanConsumerResult:
        propagated_request_id = message.fields.get(MESSAGE_REQUEST_ID_FIELD)
        scoped_request_id = propagated_request_id if is_valid_request_id(propagated_request_id) else None
        with request_id_scope(scoped_request_id):
            task = parse_scan_task_fields(message.fields)
            if task is None:
                logger.warning("scan.task.invalid message_id=%s reason=invalid_fields", message.message_id)
                await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                return ScanConsumerResult(acknowledged=1, invalid=1)

            started = time.perf_counter()
            processing_error: Exception | None = None
            try:
                logger.info(
                    "scan.task.started message_id=%s task_id=%s version_id=%s scanner_type=%s retry_count=%s request_id=%s",
                    message.message_id,
                    task.task_id,
                    task.version_id,
                    task.scanner_type,
                    task.retry_count,
                    current_request_id(),
                )
                async with engine.begin() as connection:
                    try:
                        await process_scan_task(
                            connection,
                            task,
                            scanner,
                            storage_base_path=self.storage_base_path,
                            scan_temp_dir=self.scan_temp_dir,
                            storage=self.storage,
                            mark_failed_on_error=False,
                        )
                    except Exception as exc:
                        processing_error = exc
                        raise
            except Exception as exc:
                if processing_error is None:
                    raise
                if isinstance(exc, ScanTaskLeaseUnavailable):
                    logger.info(
                        "scan.task.lease_busy message_id=%s task_id=%s version_id=%s scanner_type=%s retry_count=%s "
                        "request_id=%s elapsed_ms=%s",
                        message.message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        current_request_id(),
                        int((time.perf_counter() - started) * 1000),
                    )
                    return ScanConsumerResult()
                if isinstance(exc, ScanTaskNotReady):
                    now_millis = self.clock_millis()
                    created_at_millis = task.created_at_millis or now_millis
                    age_millis = max(now_millis - created_at_millis, 0)
                    if (
                        task.visibility_retry_count >= self.max_not_ready_requeue_count
                        or age_millis >= self.max_not_ready_age_ms
                    ):
                        logger.error(
                            "scan.task.not_ready_parked message_id=%s task_id=%s version_id=%s scanner_type=%s "
                            "retry_count=%s visibility_retry_count=%s request_id=%s failure_code=%s age_ms=%s "
                            "elapsed_ms=%s",
                            message.message_id,
                            task.task_id,
                            task.version_id,
                            task.scanner_type,
                            task.retry_count,
                            task.visibility_retry_count,
                            current_request_id(),
                            "VERSION_NOT_VISIBLE",
                            age_millis,
                            int((time.perf_counter() - started) * 1000),
                        )
                        return ScanConsumerResult(processed=1, failed=1)

                    next_visibility_retry_count = task.visibility_retry_count + 1
                    retry_message_id = await self.redis.add(
                        self.stream_key,
                        build_retry_stream_fields(
                            task,
                            retry_count=task.retry_count,
                            created_at_millis=created_at_millis,
                            visibility_retry_count=next_visibility_retry_count,
                        ),
                    )
                    logger.info(
                        "scan.task.not_ready_retry_scheduled message_id=%s retry_message_id=%s task_id=%s "
                        "version_id=%s scanner_type=%s retry_count=%s visibility_retry_count=%s request_id=%s "
                        "age_ms=%s elapsed_ms=%s",
                        message.message_id,
                        retry_message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        next_visibility_retry_count,
                        current_request_id(),
                        age_millis,
                        int((time.perf_counter() - started) * 1000),
                    )
                    await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                    return ScanConsumerResult(processed=1, acknowledged=1, retried=1)
                if isinstance(exc, ScanTaskAlreadyFinalized):
                    logger.info(
                        "scan.task.skipped_finalized message_id=%s task_id=%s version_id=%s scanner_type=%s "
                        "retry_count=%s request_id=%s elapsed_ms=%s",
                        message.message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        current_request_id(),
                        int((time.perf_counter() - started) * 1000),
                    )
                    await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                    return ScanConsumerResult(processed=1, acknowledged=1)

                if task.retry_count < MAX_SCAN_RETRY_COUNT:
                    retry_message_id = await self.redis.add(
                        self.stream_key,
                        build_retry_stream_fields(
                            task,
                            retry_count=task.retry_count + 1,
                            created_at_millis=self.clock_millis(),
                        ),
                    )
                    logger.warning(
                        "scan.task.retry_scheduled message_id=%s retry_message_id=%s task_id=%s version_id=%s "
                        "scanner_type=%s retry_count=%s next_retry_count=%s request_id=%s failure_code=%s "
                        "error_type=%s elapsed_ms=%s",
                        message.message_id,
                        retry_message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        task.retry_count + 1,
                        current_request_id(),
                        "SCANNER_ERROR",
                        type(exc).__name__,
                        int((time.perf_counter() - started) * 1000),
                    )
                    await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                    return ScanConsumerResult(processed=1, acknowledged=1, retried=1)

                try:
                    async with engine.begin() as connection:
                        await acquire_scan_task_lease(connection, task.version_id)
                        await mark_scan_task_failed(
                            connection,
                            version_id=task.version_id,
                            scanner_type=task.scanner_type,
                        )
                except ScanTaskLeaseUnavailable:
                    logger.info(
                        "scan.task.terminal_transition_deferred message_id=%s task_id=%s version_id=%s "
                        "scanner_type=%s retry_count=%s request_id=%s elapsed_ms=%s",
                        message.message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        current_request_id(),
                        int((time.perf_counter() - started) * 1000),
                    )
                    return ScanConsumerResult()
                except (ScanTaskAlreadyFinalized, ScanTaskNotReady):
                    logger.info(
                        "scan.task.terminal_transition_skipped message_id=%s task_id=%s version_id=%s "
                        "scanner_type=%s retry_count=%s request_id=%s elapsed_ms=%s",
                        message.message_id,
                        task.task_id,
                        task.version_id,
                        task.scanner_type,
                        task.retry_count,
                        current_request_id(),
                        int((time.perf_counter() - started) * 1000),
                    )
                    await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                    return ScanConsumerResult(processed=1, acknowledged=1)
                logger.error(
                    "scan.task.failed message_id=%s task_id=%s version_id=%s scanner_type=%s retry_count=%s "
                    "request_id=%s failure_code=%s error_type=%s elapsed_ms=%s",
                    message.message_id,
                    task.task_id,
                    task.version_id,
                    task.scanner_type,
                    task.retry_count,
                    current_request_id(),
                    "SCANNER_ERROR",
                    type(exc).__name__,
                    int((time.perf_counter() - started) * 1000),
                )
                await self.redis.ack(self.stream_key, self.group_name, message.message_id)
                return ScanConsumerResult(processed=1, acknowledged=1, failed=1)

            await self.redis.ack(self.stream_key, self.group_name, message.message_id)
            return ScanConsumerResult(processed=1, acknowledged=1)


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
