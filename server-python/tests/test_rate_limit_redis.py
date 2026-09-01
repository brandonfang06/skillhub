from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.rate_limit import RedisSlidingWindowRateLimiter
from app.core.redis import SkillHubRedisClient

TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


@pytest.mark.skipif(
    not TEST_REDIS_URL,
    reason="SKILLHUB_TEST_REDIS_URL is required for Redis integration",
)
@pytest.mark.anyio
async def test_redis_sliding_window_is_atomic_for_same_millisecond_requests() -> None:
    assert TEST_REDIS_URL is not None
    raw_client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_client)
    limiter = RedisSlidingWindowRateLimiter(redis_client)
    key = f"ratelimit:test:{uuid4().hex}"
    try:
        decisions = await asyncio.gather(
            *(
                limiter.try_acquire(
                    key=key,
                    limit=2,
                    window_seconds=60,
                    member=f"request-{index}",
                )
                for index in range(3)
            )
        )

        assert sum(decisions) == 2
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()
