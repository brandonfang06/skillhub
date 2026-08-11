from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from app.core.request_id import (
    MESSAGE_REQUEST_ID_FIELD,
    current_request_id,
    is_valid_request_id,
)
from app.publish.side_effects import ScanTaskPayload

DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"
OWNED_TRANSPORT_FIELDS = {MESSAGE_REQUEST_ID_FIELD, "traceparent", "tracestate", "baggage"}
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class RedisTarget:
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    database: int = 0


def build_scan_stream_fields(task: ScanTaskPayload) -> dict[str, str]:
    fields = {
        "taskId": task.task_id,
        "versionId": str(task.version_id),
        "publisherId": task.publisher_id or "",
        "createdAtMillis": str(task.created_at_millis),
    }
    if task.skill_path:
        fields["skillPath"] = task.skill_path
    if task.bundle_key:
        fields["bundleKey"] = task.bundle_key
    fields.update(
        (key, value)
        for key, value in (task.metadata or {}).items()
        if key not in OWNED_TRANSPORT_FIELDS
    )
    request_id = current_request_id()
    if is_valid_request_id(request_id):
        fields[MESSAGE_REQUEST_ID_FIELD] = request_id
    return fields


def encode_resp_command(arguments: list[str]) -> bytes:
    chunks = [f"*{len(arguments)}\r\n".encode("ascii")]
    for argument in arguments:
        data = argument.encode("utf-8")
        chunks.append(f"${len(data)}\r\n".encode("ascii"))
        chunks.append(data)
        chunks.append(b"\r\n")
    return b"".join(chunks)


def parse_redis_target(redis_url: str) -> RedisTarget:
    parsed = urlparse(redis_url)
    if parsed.scheme != "redis":
        raise ValueError("Only redis:// URLs are supported")
    path = parsed.path or ""
    database = 0
    if path not in {"", "/"}:
        database_text = path.lstrip("/")
        if not database_text.isdecimal():
            raise ValueError("Redis database must be numeric")
        database = int(database_text)
    return RedisTarget(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        database=database,
    )


async def open_redis_connection(target: RedisTarget) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection(target.host, target.port)
    try:
        if target.password:
            auth_arguments = ["AUTH", target.password] if target.username is None else ["AUTH", target.username, target.password]
            writer.write(encode_resp_command(auth_arguments))
            await writer.drain()
            await read_resp(reader)
        if target.database:
            writer.write(encode_resp_command(["SELECT", str(target.database)]))
            await writer.drain()
            await read_resp(reader)
        return reader, writer
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise


async def read_resp(reader: asyncio.StreamReader) -> Any:
    line = await reader.readline()
    if not line:
        raise ValueError("Redis closed the connection")
    prefix = line[:1]
    body = line[1:].rstrip(b"\r\n")
    if prefix == b"+":
        return body.decode("utf-8")
    if prefix == b"-":
        raise ValueError(body.decode("utf-8"))
    if prefix == b":":
        return int(body)
    if prefix == b"$":
        length = int(body)
        if length < 0:
            return None
        payload = await reader.readexactly(length + 2)
        if not payload.endswith(b"\r\n"):
            raise ValueError("Malformed Redis bulk string response")
        return payload[:-2].decode("utf-8")
    if prefix == b"*":
        length = int(body)
        if length < 0:
            return None
        return [await read_resp(reader) for _ in range(length)]
    raise ValueError(f"Unsupported Redis response: {line!r}")


class RedisScanTaskPublisher:
    def __init__(self, redis_client: Any, stream_key: str = DEFAULT_SCAN_STREAM_KEY) -> None:
        self.redis_client = redis_client
        self.stream_key = stream_key

    async def publish_scan_task(self, task: ScanTaskPayload) -> None:
        fields = build_scan_stream_fields(task)
        response = await self.redis_client.xadd(self.stream_key, fields)
        if response is None:
            raise ValueError("Redis XADD returned null")
        logger.info(
            "scan.task.enqueued stream=%s message_id=%s task_id=%s version_id=%s scanner_type=%s has_bundle=%s has_skill_path=%s request_id=%s",
            self.stream_key,
            response,
            task.task_id,
            task.version_id,
            task.metadata.get("scannerType", "skill-scanner"),
            task.bundle_key is not None,
            task.skill_path is not None,
            current_request_id(),
        )
