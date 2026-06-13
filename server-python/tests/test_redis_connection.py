from __future__ import annotations

import asyncio

import pytest

from app.publish.scanner_handoff import RedisTarget, open_redis_connection, parse_redis_target


def test_parse_redis_target_supports_password_and_database() -> None:
    target = parse_redis_target("redis://:redis%20secret@redis.internal:6380/2")

    assert target == RedisTarget(
        host="redis.internal",
        port=6380,
        username=None,
        password="redis secret",
        database=2,
    )


def test_parse_redis_target_supports_acl_username_password() -> None:
    target = parse_redis_target("redis://skillhub:redis-secret@redis.internal:6379/0")

    assert target.username == "skillhub"
    assert target.password == "redis-secret"
    assert target.database == 0


@pytest.mark.anyio
async def test_open_redis_connection_authenticates_and_selects_database(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[bytes] = []

    class FakeReader:
        def __init__(self) -> None:
            self.responses = [b"+OK\r\n", b"+OK\r\n"]

        async def readline(self) -> bytes:
            return self.responses.pop(0)

    class FakeWriter:
        def write(self, payload: bytes) -> None:
            writes.append(payload)

        async def drain(self) -> None:
            return None

    async def fake_open_connection(host: str, port: int) -> tuple[FakeReader, FakeWriter]:
        assert host == "redis.internal"
        assert port == 6380
        return FakeReader(), FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    await open_redis_connection(RedisTarget("redis.internal", 6380, None, "redis secret", 2))

    assert writes == [
        b"*2\r\n$4\r\nAUTH\r\n$12\r\nredis secret\r\n",
        b"*2\r\n$6\r\nSELECT\r\n$1\r\n2\r\n",
    ]
