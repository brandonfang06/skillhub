from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any


def _escape_sse_lines(value: str) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def format_sse_event(event: str, data: str) -> str:
    event_name = _escape_sse_lines(event).split("\n", 1)[0]
    payload = "".join(f"data: {line}\n" for line in _escape_sse_lines(data).split("\n"))
    return f"event: {event_name}\n{payload}\n"


def format_sse_comment(comment: str) -> str:
    line = _escape_sse_lines(comment).split("\n", 1)[0]
    return f": {line}\n\n"


class NotificationFanoutManager:
    def __init__(self, *, max_connections_per_user: int = 5, max_total_connections: int = 1000) -> None:
        self.max_connections_per_user = max_connections_per_user
        self.max_total_connections = max_total_connections
        self._connections: dict[str, deque[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(deque)
        self._total_connections = 0

    def total_connections(self) -> int:
        return self._total_connections

    def connection_count(self, user_id: str) -> int:
        return len(self._connections.get(user_id, ()))

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        queues = list(self._connections.get(str(user_id), ()))
        for queue in queues:
            queue.put_nowait(dict(payload))

    async def stream(
        self,
        user_id: str,
        *,
        is_disconnected: Callable[[], Awaitable[bool]],
        heartbeat_interval: float,
    ) -> AsyncIterator[str]:
        queue = self._register(str(user_id))
        try:
            yield format_sse_event("connected", "ok")
            while not await is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                except TimeoutError:
                    yield format_sse_comment("ping")
                    continue
                if payload is None:
                    return
                yield format_sse_event("notification", json.dumps(payload, separators=(",", ":"), default=str))
        finally:
            self._cleanup(str(user_id), queue)

    def _register(self, user_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        if self._total_connections >= self.max_total_connections:
            raise RuntimeError("SSE connection limit reached")
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        user_queues = self._connections[user_id]
        if len(user_queues) >= self.max_connections_per_user:
            oldest = user_queues.popleft()
            oldest.put_nowait(None)
            self._total_connections -= 1
        user_queues.append(queue)
        self._total_connections += 1
        return queue

    def _cleanup(self, user_id: str, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        user_queues = self._connections.get(user_id)
        if user_queues is None:
            return
        try:
            user_queues.remove(queue)
        except ValueError:
            return
        self._total_connections -= 1
        if not user_queues:
            self._connections.pop(user_id, None)
