from __future__ import annotations

from typing import Any

import pytest
from redis.asyncio.retry import Retry
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import get_settings
from app.core.redis import SkillHubRedisClient, create_redis_client


def assert_resilient_redis_kwargs(kwargs: dict[str, Any]) -> None:
    assert kwargs["health_check_interval"] == 30
    assert kwargs["retry_on_error"] == [RedisConnectionError, RedisTimeoutError]
    assert isinstance(kwargs["retry"], Retry)


def assert_dict_includes(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, value in expected.items():
        assert actual[key] == value


def test_create_redis_client_uses_explicit_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeRedis:
        @staticmethod
        def from_url(url: str, **kwargs: Any) -> str:
            calls.append((url, kwargs))
            return "single-client"

    monkeypatch.setattr("app.core.redis.Redis", FakeRedis)
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://:secret@redis.single:6379/2")

    client = create_redis_client(get_settings())

    assert isinstance(client, SkillHubRedisClient)
    assert client.raw_client == "single-client"
    assert calls[0][0] == "redis://:secret@redis.single:6379/2"
    assert_dict_includes(
        calls[0][1],
        {
            "decode_responses": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
    )
    assert_resilient_redis_kwargs(calls[0][1])


def test_create_redis_client_uses_acl_username_in_split_single_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeRedis:
        @staticmethod
        def from_url(url: str, **kwargs: Any) -> str:
            calls.append((url, kwargs))
            return "single-client"

    monkeypatch.setattr("app.core.redis.Redis", FakeRedis)
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_HOST", "redis.acl")
    monkeypatch.setenv("SPRING_DATA_REDIS_USERNAME", "skillhub")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "secret")

    client = create_redis_client(get_settings())

    assert client.raw_client == "single-client"
    assert calls[0][0] == "redis://skillhub:secret@redis.acl:6379/0"
    assert_dict_includes(
        calls[0][1],
        {
            "decode_responses": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
    )
    assert_resilient_redis_kwargs(calls[0][1])


def test_create_redis_client_uses_sentinel_master(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class FakeSentinel:
        def __init__(self, sentinels: list[tuple[str, int]], **kwargs: Any) -> None:
            calls["sentinels"] = sentinels
            calls["kwargs"] = kwargs

        def master_for(self, service_name: str, **kwargs: Any) -> str:
            calls["service_name"] = service_name
            calls["master_kwargs"] = kwargs
            return "sentinel-master-client"

    monkeypatch.setattr("app.core.redis.Sentinel", FakeSentinel)
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "sentinel-a:26379, sentinel-b:26380")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_USERNAME", "sentinel-user")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_PASSWORD", "sentinel-secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_USERNAME", "skillhub")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_DATABASE", "4")
    monkeypatch.setenv("SPRING_DATA_REDIS_SSL_ENABLED", "true")
    monkeypatch.setenv("SPRING_DATA_REDIS_CONNECT_TIMEOUT", "PT7S")
    monkeypatch.setenv("SPRING_DATA_REDIS_TIMEOUT", "PT9S")

    client = create_redis_client(get_settings())

    assert client.raw_client == "sentinel-master-client"
    assert calls["sentinels"] == [("sentinel-a", 26379), ("sentinel-b", 26380)]
    assert_dict_includes(
        calls["kwargs"],
        {
            "username": "skillhub",
            "password": "secret",
            "socket_connect_timeout": 7,
            "socket_timeout": 9,
            "decode_responses": True,
            "ssl": True,
        },
    )
    assert_dict_includes(
        calls["kwargs"]["sentinel_kwargs"],
        {
            "username": "sentinel-user",
            "password": "sentinel-secret",
            "socket_connect_timeout": 7,
            "socket_timeout": 9,
            "decode_responses": True,
            "ssl": True,
        },
    )
    assert_resilient_redis_kwargs(calls["kwargs"])
    assert_resilient_redis_kwargs(calls["kwargs"]["sentinel_kwargs"])
    assert calls["service_name"] == "mymaster"
    assert_dict_includes(
        calls["master_kwargs"],
        {
            "username": "skillhub",
            "password": "secret",
            "db": 4,
            "socket_connect_timeout": 7,
            "socket_timeout": 9,
            "decode_responses": True,
            "ssl": True,
        },
    )
    assert_resilient_redis_kwargs(calls["master_kwargs"])


def test_create_redis_client_parses_default_sentinel_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class FakeSentinel:
        def __init__(self, sentinels: list[tuple[str, int]], **kwargs: Any) -> None:
            calls["sentinels"] = sentinels

        def master_for(self, service_name: str, **kwargs: Any) -> str:
            return "sentinel-master-client"

    monkeypatch.setattr("app.core.redis.Sentinel", FakeSentinel)
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "sentinel-a")

    create_redis_client(get_settings())

    assert calls["sentinels"] == [("sentinel-a", 26379)]


@pytest.mark.anyio
async def test_redis_client_exposes_transaction_and_variadic_delete_contract() -> None:
    calls: list[tuple[object, ...]] = []
    pipeline = object()

    class FakeRawClient:
        def pipeline(self, *, transaction: bool) -> object:
            calls.append(("pipeline", transaction))
            return pipeline

        async def delete(self, *keys: str) -> None:
            calls.append(("delete", *keys))

    client = SkillHubRedisClient(FakeRawClient())

    assert client.pipeline(transaction=True) is pipeline
    await client.delete("session:first", "session:second")

    assert calls == [
        ("pipeline", True),
        ("delete", "session:first", "session:second"),
    ]


@pytest.mark.anyio
async def test_redis_client_closes_sentinel_node_clients() -> None:
    closed: list[str] = []

    class FakeClosable:
        def __init__(self, name: str) -> None:
            self.name = name

        async def aclose(self) -> None:
            closed.append(self.name)

    client = SkillHubRedisClient(
        FakeClosable("master"),
        close_clients=[FakeClosable("sentinel-a"), FakeClosable("sentinel-b")],
    )

    await client.aclose()

    assert closed == ["master", "sentinel-a", "sentinel-b"]
