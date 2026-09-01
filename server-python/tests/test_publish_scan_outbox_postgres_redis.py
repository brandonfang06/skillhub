from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.redis import SkillHubRedisClient
from app.publish.scan_outbox import ScanOutboxDispatcher
from app.publish.scan_worker import (
    ScanTaskAlreadyFinalized,
    SecurityScanTask,
    process_scan_task,
)
from app.publish.scanner_handoff import RedisScanTaskPublisher

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


@dataclass(frozen=True)
class ScanFixture:
    user_id: str
    namespace_id: int
    skill_id: int
    version_id: int
    task_id: str


async def _create_scan_fixture(
    engine: AsyncEngine,
    *,
    suffix: str,
    now: datetime,
    outbox_status: str | None = "PENDING",
    lease_until: datetime | None = None,
    scanned_at: datetime | None = None,
) -> ScanFixture:
    user_id = f"outbox-real-{suffix}"
    task_id = f"outbox-task-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO user_account (id, display_name)
                VALUES (:user_id, 'Outbox real-service test')
                """
            ),
            {"user_id": user_id},
        )
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (
                            slug, display_name, type, status, created_by
                        )
                        VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :user_id)
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
                        INSERT INTO skill (
                            namespace_id, slug, owner_id, visibility, status,
                            created_by, updated_by
                        )
                        VALUES (
                            :namespace_id, :slug, :user_id, 'PRIVATE', 'ACTIVE',
                            :user_id, :user_id
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "namespace_id": namespace_id,
                        "slug": user_id,
                        "user_id": user_id,
                    },
                )
            ).scalar_one()
        )
        version_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_version (
                            skill_id, version, status, created_by
                        )
                        VALUES (:skill_id, '1.0.0', 'SCANNING', :user_id)
                        RETURNING id
                        """
                    ),
                    {"skill_id": skill_id, "user_id": user_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO security_audit (
                    skill_version_id, scanner_type, task_id, verdict, is_safe,
                    findings_count, findings, scanned_at
                )
                VALUES (
                    :version_id, 'SKILL_SCANNER', :task_id, 'SUSPICIOUS', FALSE,
                    0, '[]'::jsonb, :scanned_at
                )
                """
            ),
            {
                "version_id": version_id,
                "task_id": task_id,
                "scanned_at": scanned_at,
            },
        )
        if outbox_status is not None:
            await connection.execute(
                text(
                    """
                    INSERT INTO scan_task_outbox (
                        task_id, version_id, skill_path, publisher_id, metadata,
                        status, retry_count, next_attempt_at, lease_until,
                        created_at, updated_at, entity_version
                    )
                    VALUES (
                        :task_id, :version_id, :skill_path, :publisher_id,
                        '{"scannerType":"skill-scanner"}'::jsonb,
                        :status, 0, :now, :lease_until, :now, :now, 0
                    )
                    """
                ),
                {
                    "task_id": task_id,
                    "version_id": version_id,
                    "skill_path": "/tmp/skillhub-outbox-test",
                    "publisher_id": user_id,
                    "status": outbox_status,
                    "now": now,
                    "lease_until": lease_until,
                },
            )
    return ScanFixture(user_id, namespace_id, skill_id, version_id, task_id)


async def _cleanup_scan_fixture(
    engine: AsyncEngine,
    fixture: ScanFixture,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM scan_task_outbox WHERE publisher_id = :user_id"),
            {"user_id": fixture.user_id},
        )
        await connection.execute(
            text(
                """
                DELETE FROM local_security_scan_execution
                WHERE security_audit_id IN (
                    SELECT id FROM security_audit
                    WHERE skill_version_id = :version_id
                )
                """
            ),
            {"version_id": fixture.version_id},
        )
        await connection.execute(
            text("DELETE FROM security_audit WHERE skill_version_id = :version_id"),
            {"version_id": fixture.version_id},
        )
        await connection.execute(
            text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text("DELETE FROM skill_version WHERE id = :version_id"),
            {"version_id": fixture.version_id},
        )
        await connection.execute(
            text("DELETE FROM skill WHERE id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text("DELETE FROM namespace WHERE id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM user_account WHERE id = :user_id"),
            {"user_id": fixture.user_id},
        )


def _unavailable_redis_client() -> SkillHubRedisClient:
    return SkillHubRedisClient(
        Redis.from_url(
            "redis://127.0.0.1:1/0",
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    )


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_real_outbox_retries_redis_outage_then_delivers_once() -> None:
    suffix = uuid4().hex[:12]
    now = datetime.now(UTC)
    stream_key = f"skillhub:test:outbox-retry:{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))
    raw_redis = Redis.from_url(str(TEST_REDIS_URL), decode_responses=True)
    healthy_redis = SkillHubRedisClient(raw_redis)
    unavailable_redis = _unavailable_redis_client()
    fixture = await _create_scan_fixture(engine, suffix=suffix, now=now)

    try:
        await healthy_redis.delete(stream_key)
        failed_dispatch = await ScanOutboxDispatcher(
            engine,
            RedisScanTaskPublisher(unavailable_redis, stream_key),
            max_attempts=3,
        ).dispatch_once(now=now)

        async with engine.connect() as connection:
            retry_row = (
                await connection.execute(
                    text(
                        """
                        SELECT status, retry_count, next_attempt_at, last_error
                        FROM scan_task_outbox
                        WHERE task_id = :task_id
                        """
                    ),
                    {"task_id": fixture.task_id},
                )
            ).mappings().one()

        assert failed_dispatch.retried == 1
        assert retry_row["status"] == "PENDING"
        assert retry_row["retry_count"] == 1
        assert retry_row["next_attempt_at"] == now + timedelta(seconds=2)
        assert retry_row["last_error"]
        assert await raw_redis.xlen(stream_key) == 0

        recovered_dispatch = await ScanOutboxDispatcher(
            engine,
            RedisScanTaskPublisher(healthy_redis, stream_key),
            max_attempts=3,
        ).dispatch_once(now=now + timedelta(seconds=2))
        messages = await raw_redis.xrange(stream_key)

        assert recovered_dispatch.sent == 1
        assert len(messages) == 1
        assert messages[0][1]["taskId"] == fixture.task_id
        async with engine.connect() as connection:
            assert (
                await connection.execute(
                    text(
                        "SELECT status FROM scan_task_outbox WHERE task_id = :task_id"
                    ),
                    {"task_id": fixture.task_id},
                )
            ).scalar_one() == "SENT"
    finally:
        await healthy_redis.delete(stream_key)
        await unavailable_redis.aclose()
        await healthy_redis.aclose()
        await _cleanup_scan_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_real_outbox_reclaims_expired_lease_and_cleans_only_old_sent() -> None:
    suffix = uuid4().hex[:12]
    now = datetime.now(UTC)
    stream_key = f"skillhub:test:outbox-reclaim:{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))
    raw_redis = Redis.from_url(str(TEST_REDIS_URL), decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    fixture = await _create_scan_fixture(
        engine,
        suffix=suffix,
        now=now,
        outbox_status="SENDING",
        lease_until=now - timedelta(seconds=1),
    )
    recent_task_id = f"recent-task-{suffix}"

    try:
        await redis_client.delete(stream_key)
        dispatcher = ScanOutboxDispatcher(
            engine,
            RedisScanTaskPublisher(redis_client, stream_key),
        )
        reclaimed = await dispatcher.dispatch_once(now=now)

        assert reclaimed.sent == 1
        assert await raw_redis.xlen(stream_key) == 1

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE scan_task_outbox
                    SET updated_at = :old_updated_at
                    WHERE task_id = :task_id
                    """
                ),
                {
                    "task_id": fixture.task_id,
                    "old_updated_at": now - timedelta(days=8),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO scan_task_outbox (
                        task_id, version_id, publisher_id, metadata, status,
                        retry_count, next_attempt_at, created_at, updated_at
                    )
                    VALUES (
                        :task_id, :version_id, :publisher_id, '{}'::jsonb,
                        'SENT', 0, :now, :now, :now
                    )
                    """
                ),
                {
                    "task_id": recent_task_id,
                    "version_id": fixture.version_id,
                    "publisher_id": fixture.user_id,
                    "now": now,
                },
            )

        assert await dispatcher.cleanup_sent(retention_days=7, now=now) == 1
        async with engine.connect() as connection:
            remaining = set(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT task_id
                            FROM scan_task_outbox
                            WHERE publisher_id = :publisher_id
                            """
                        ),
                        {"publisher_id": fixture.user_id},
                    )
                ).scalars().all()
            )
        assert remaining == {recent_task_id}
    finally:
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        await _cleanup_scan_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_real_outbox_terminal_failure_and_processed_task_id_are_safe() -> None:
    suffix = uuid4().hex[:12]
    now = datetime.now(UTC)
    engine = create_async_engine(str(TEST_DATABASE_URL))
    unavailable_redis = _unavailable_redis_client()
    fixture = await _create_scan_fixture(engine, suffix=suffix, now=now)

    try:
        terminal = await ScanOutboxDispatcher(
            engine,
            RedisScanTaskPublisher(unavailable_redis, f"unused:{suffix}"),
            max_attempts=1,
        ).dispatch_once(now=now)

        async with engine.connect() as connection:
            outbox_row = (
                await connection.execute(
                    text(
                        """
                        SELECT status, retry_count, last_error
                        FROM scan_task_outbox
                        WHERE task_id = :task_id
                        """
                    ),
                    {"task_id": fixture.task_id},
                )
            ).mappings().one()
            version_status = (
                await connection.execute(
                    text("SELECT status FROM skill_version WHERE id = :version_id"),
                    {"version_id": fixture.version_id},
                )
            ).scalar_one()
            execution_row = (
                await connection.execute(
                    text(
                        """
                        SELECT execution.scan_status, execution.failure_code
                        FROM local_security_scan_execution execution
                        JOIN security_audit audit
                          ON audit.id = execution.security_audit_id
                        WHERE audit.task_id = :task_id
                        """
                    ),
                    {"task_id": fixture.task_id},
                )
            ).mappings().one_or_none()

        assert terminal.failed == 1
        assert outbox_row["status"] == "FAILED"
        assert outbox_row["retry_count"] == 1
        assert outbox_row["last_error"]
        assert version_status == "SCAN_FAILED"
        assert execution_row is not None
        assert execution_row["scan_status"] == "FAILED"
        assert execution_row["failure_code"] == "OUTBOX_DELIVERY_FAILED"

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE skill_version
                    SET status = 'SCANNING'
                    WHERE id = :version_id
                    """
                ),
                {"version_id": fixture.version_id},
            )
            await connection.execute(
                text(
                    """
                    UPDATE security_audit
                    SET scanned_at = :scanned_at
                    WHERE task_id = :task_id
                    """
                ),
                {"task_id": fixture.task_id, "scanned_at": now},
            )

        class ScannerMustNotRun:
            async def scan(self, task: SecurityScanTask, skill_path: str) -> None:
                raise AssertionError("processed task ID reached scanner")

        async with engine.begin() as connection:
            with pytest.raises(ScanTaskAlreadyFinalized, match="already processed"):
                await process_scan_task(
                    connection,
                    SecurityScanTask(
                        task_id=fixture.task_id,
                        version_id=fixture.version_id,
                        skill_path="unused",
                    ),
                    ScannerMustNotRun(),
                    storage_base_path="unused",
                    scan_temp_dir="unused",
                )
    finally:
        await unavailable_redis.aclose()
        await _cleanup_scan_fixture(engine, fixture)
        await engine.dispose()
