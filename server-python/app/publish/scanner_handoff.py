from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse

from app.publish.side_effects import ScanTaskPayload


DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"


@dataclass(frozen=True)
class RedisTarget:
    host: str
    port: int


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
    fields.update(task.metadata or {})
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
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError("Redis auth and DB selection are not supported by the publish handoff adapter")
    return RedisTarget(host=parsed.hostname or "localhost", port=parsed.port or 6379)


class RedisScanTaskPublisher:
    def __init__(self, redis_url: str, stream_key: str = DEFAULT_SCAN_STREAM_KEY) -> None:
        self.target = parse_redis_target(redis_url)
        self.stream_key = stream_key

    async def publish_scan_task(self, task: ScanTaskPayload) -> None:
        fields = build_scan_stream_fields(task)
        arguments = ["XADD", self.stream_key, "*"]
        for key, value in fields.items():
            arguments.extend([key, value])

        reader, writer = await asyncio.open_connection(self.target.host, self.target.port)
        try:
            writer.write(encode_resp_command(arguments))
            await writer.drain()
            line = await reader.readline()
            if not line.startswith(b"$"):
                raise ValueError(f"Unexpected Redis XADD response: {line!r}")
            length = int(line[1:].strip())
            if length < 0:
                raise ValueError("Redis XADD returned null")
            payload = await reader.readexactly(length + 2)
            if not payload.endswith(b"\r\n"):
                raise ValueError("Malformed Redis bulk string response")
        finally:
            writer.close()
            await writer.wait_closed()
