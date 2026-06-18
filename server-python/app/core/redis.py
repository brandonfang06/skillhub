from __future__ import annotations

from typing import Any

from redis.asyncio import Redis, Sentinel

from app.core.config import Settings

DEFAULT_SENTINEL_PORT = 26379


class SkillHubRedisClient:
    def __init__(self, raw_client: Any) -> None:
        self.raw_client = raw_client

    async def execute_command(self, *arguments: object) -> Any:
        return await self.raw_client.execute_command(*arguments)

    async def xadd(self, stream_key: str, fields: dict[str, str]) -> str:
        return str(await self.raw_client.xadd(stream_key, fields))

    async def xgroup_create(self, stream_key: str, group_name: str, *, id: str = "0", mkstream: bool = True) -> None:
        await self.raw_client.xgroup_create(stream_key, group_name, id=id, mkstream=mkstream)

    async def xreadgroup(
        self,
        group_name: str,
        consumer_name: str,
        streams: dict[str, str],
        *,
        count: int,
        block_ms: int,
    ) -> Any:
        return await self.raw_client.xreadgroup(group_name, consumer_name, streams, count=count, block=block_ms)

    async def xautoclaim(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        *,
        min_idle_ms: int,
        start_id: str,
        count: int,
    ) -> Any:
        return await self.raw_client.xautoclaim(
            stream_key,
            group_name,
            consumer_name,
            min_idle_ms,
            start_id=start_id,
            count=count,
        )

    async def xack(self, stream_key: str, group_name: str, message_id: str) -> None:
        await self.raw_client.xack(stream_key, group_name, message_id)

    async def get(self, key: str) -> str | None:
        value = await self.raw_client.get(key)
        return None if value is None else str(value)

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        response = await self.raw_client.set(key, value, ex=ex, nx=nx)
        return bool(response)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        await self.raw_client.setex(key, ttl_seconds, value)

    async def delete(self, key: str) -> None:
        await self.raw_client.delete(key)

    async def aclose(self) -> None:
        close = getattr(self.raw_client, "aclose", None)
        if close is not None:
            await close()


def create_redis_client(settings: Settings) -> SkillHubRedisClient:
    if getattr(settings, "redis_mode", "single") == "sentinel":
        sentinel = Sentinel(
            _parse_sentinel_nodes(getattr(settings, "redis_sentinel_nodes", [])),
            sentinel_kwargs=_sentinel_client_kwargs(settings),
            **_shared_client_kwargs(settings),
        )
        return SkillHubRedisClient(
            sentinel.master_for(
                getattr(settings, "redis_sentinel_master", ""),
                db=getattr(settings, "redis_database", 0),
                **_shared_client_kwargs(settings),
            )
        )
    return SkillHubRedisClient(
        Redis.from_url(
            getattr(settings, "redis_url"),
            decode_responses=True,
            socket_connect_timeout=getattr(settings, "redis_connect_timeout_seconds", 5),
            socket_timeout=getattr(settings, "redis_timeout_seconds", 5),
        )
    )


def _shared_client_kwargs(settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "socket_connect_timeout": getattr(settings, "redis_connect_timeout_seconds", 5),
        "socket_timeout": getattr(settings, "redis_timeout_seconds", 5),
        "decode_responses": True,
    }
    if getattr(settings, "redis_username", ""):
        kwargs["username"] = getattr(settings, "redis_username")
    if getattr(settings, "redis_password", ""):
        kwargs["password"] = getattr(settings, "redis_password")
    if getattr(settings, "redis_ssl_enabled", False):
        kwargs["ssl"] = True
    return kwargs


def _sentinel_client_kwargs(settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "socket_connect_timeout": getattr(settings, "redis_connect_timeout_seconds", 5),
        "socket_timeout": getattr(settings, "redis_timeout_seconds", 5),
        "decode_responses": True,
    }
    if getattr(settings, "redis_sentinel_username", ""):
        kwargs["username"] = getattr(settings, "redis_sentinel_username")
    if getattr(settings, "redis_sentinel_password", ""):
        kwargs["password"] = getattr(settings, "redis_sentinel_password")
    if getattr(settings, "redis_ssl_enabled", False):
        kwargs["ssl"] = True
    return kwargs


def _parse_sentinel_nodes(nodes: list[str]) -> list[tuple[str, int]]:
    parsed_nodes: list[tuple[str, int]] = []
    for node in nodes:
        host, separator, port_text = node.rpartition(":")
        if separator == "":
            parsed_nodes.append((node, DEFAULT_SENTINEL_PORT))
            continue
        parsed_nodes.append((host, int(port_text)))
    return parsed_nodes
