from __future__ import annotations

from typing import Any

import pytest

from app.core.config import get_settings
from app.core.redis import SkillHubRedisClient, create_redis_client


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
    assert calls == [
        (
            "redis://:secret@redis.single:6379/2",
            {
                "decode_responses": True,
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
            },
        )
    ]


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
    assert calls == [
        (
            "redis://skillhub:secret@redis.acl:6379/0",
            {
                "decode_responses": True,
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
            },
        )
    ]


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
    assert calls["kwargs"] == {
        "username": "skillhub",
        "password": "secret",
        "socket_connect_timeout": 7,
        "socket_timeout": 9,
        "decode_responses": True,
        "ssl": True,
        "sentinel_kwargs": {
            "username": "sentinel-user",
            "password": "sentinel-secret",
            "socket_connect_timeout": 7,
            "socket_timeout": 9,
            "decode_responses": True,
            "ssl": True,
        },
    }
    assert calls["service_name"] == "mymaster"
    assert calls["master_kwargs"] == {
        "username": "skillhub",
        "password": "secret",
        "db": 4,
        "socket_connect_timeout": 7,
        "socket_timeout": 9,
        "decode_responses": True,
        "ssl": True,
    }


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
