from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.redis import SkillHubRedisClient
from app.publish.scan_consumer import (
    MAX_SCAN_RETRY_COUNT,
    RedisStreamClient,
    ScanConsumerRuntime,
)
from app.publish.scan_worker import SecurityScanTask

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


class TimeoutScanner:
    async def scan(self, task: SecurityScanTask, skill_path: str) -> None:
        raise httpx.ReadTimeout("LiteLLM analysis timed out")


async def _create_scanning_version(engine: AsyncEngine, suffix: str) -> tuple[str, int, int, int]:
    user_id = f"scan-timeout-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO user_account (id, display_name) VALUES (:user_id, 'Scan timeout integration')"),
            {"user_id": user_id},
        )
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, created_by)
                        VALUES (:slug, :slug, 'TEAM', :user_id)
                        RETURNING id
                        """
                    ),
                    {"slug": user_id, "user_id": user_id},
                )
            ).scalar_one()
        )
        skill_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill (namespace_id, slug, owner_id, created_by, updated_by)
                        VALUES (:namespace_id, :slug, :user_id, :user_id, :user_id)
                        RETURNING id
                        """
                    ),
                    {"namespace_id": namespace_id, "slug": user_id, "user_id": user_id},
                )
            ).scalar_one()
        )
        version_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_version (skill_id, version, status, created_by)
                        VALUES (:skill_id, '1.0.0', 'SCANNING', :user_id)
                        RETURNING id
                        """
                    ),
                    {"skill_id": skill_id, "user_id": user_id},
                )
            ).scalar_one()
        )
    return user_id, namespace_id, skill_id, version_id


async def _cleanup_scanning_version(
    engine: AsyncEngine,
    *,
    user_id: str,
    namespace_id: int,
    skill_id: int,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
            {"skill_id": skill_id},
        )
        await connection.execute(
            text("DELETE FROM skill_version WHERE skill_id = :skill_id"),
            {"skill_id": skill_id},
        )
        await connection.execute(text("DELETE FROM skill WHERE id = :skill_id"), {"skill_id": skill_id})
        await connection.execute(
            text("DELETE FROM namespace WHERE id = :namespace_id"),
            {"namespace_id": namespace_id},
        )
        await connection.execute(text("DELETE FROM user_account WHERE id = :user_id"), {"user_id": user_id})


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_litellm_timeout_at_max_retry_commits_scan_failed_with_real_services(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan-timeout:{suffix}"
    group_name = f"scan-timeout-{suffix}"
    skill_path = tmp_path / "skill"
    skill_path.mkdir()
    engine = create_async_engine(TEST_DATABASE_URL)
    raw_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    user_id, namespace_id, skill_id, version_id = await _create_scanning_version(engine, suffix)

    try:
        await redis_client.xadd(
            stream_key,
            {
                "taskId": f"task-{suffix}",
                "versionId": str(version_id),
                "skillPath": str(skill_path),
                "retryCount": str(MAX_SCAN_RETRY_COUNT),
                "scannerType": "skill-scanner",
            },
        )
        runtime = ScanConsumerRuntime(
            RedisStreamClient(redis_client),
            stream_key=stream_key,
            group_name=group_name,
            consumer_name=f"consumer-{suffix}",
            storage_base_path=str(tmp_path),
            scan_temp_dir=str(tmp_path / "scans"),
        )

        async with engine.begin() as connection:
            result = await runtime.consume_once(connection, TimeoutScanner(), count=1, block_ms=100)

        async with engine.connect() as connection:
            status = (
                await connection.execute(
                    text("SELECT status FROM skill_version WHERE id = :version_id"),
                    {"version_id": version_id},
                )
            ).scalar_one()

        assert result.failed == 1
        assert result.acknowledged == 1
        assert result.retried == 0
        assert status == "SCAN_FAILED"
    finally:
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        await _cleanup_scanning_version(
            engine,
            user_id=user_id,
            namespace_id=namespace_id,
            skill_id=skill_id,
        )
        await engine.dispose()
