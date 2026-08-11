from __future__ import annotations

import asyncio
import os
from types import TracebackType
from typing import Any
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.redis import SkillHubRedisClient
from app.publish.scan_consumer import (
    MAX_SCAN_RETRY_COUNT,
    RedisStreamClient,
    ScanConsumerResult,
    ScanConsumerRuntime,
)
from app.publish.scan_worker import (
    ScanTaskLeaseUnavailable,
    SecurityScanTask,
    process_scan_task,
)
from app.publish.scanner_result import (
    SecurityScanResultInput,
    apply_security_scan_result,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


class TimeoutScanner:
    async def scan(self, task: SecurityScanTask, skill_path: str) -> None:
        raise httpx.ReadTimeout("LiteLLM analysis timed out")


class SafeScanner:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
        self.calls += 1
        return SecurityScanResultInput(
            scan_id=f"safe-{task.version_id}",
            verdict="SAFE",
            findings_count=0,
            max_severity=None,
            findings=[],
            scan_duration_seconds=0.01,
            analyzers_requested=["static_analyzer"],
            analyzers_completed=["static_analyzer"],
        )


async def _insert_scanning_version(connection: AsyncConnection, suffix: str) -> tuple[str, int, int, int]:
    user_id = f"scan-timeout-{suffix}"
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
    await connection.execute(
        text(
            """
            INSERT INTO security_audit (
                skill_version_id, scanner_type, verdict, is_safe, findings_count, findings
            ) VALUES (
                :version_id, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb
            )
            """
        ),
        {"version_id": version_id},
    )
    return user_id, namespace_id, skill_id, version_id


async def _create_scanning_version(engine: AsyncEngine, suffix: str) -> tuple[str, int, int, int]:
    async with engine.begin() as connection:
        return await _insert_scanning_version(connection, suffix)


async def _cleanup_scanning_version(
    engine: AsyncEngine,
    *,
    user_id: str,
    namespace_id: int,
    skill_id: int,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                DELETE FROM local_security_scan_execution
                WHERE security_audit_id IN (
                    SELECT id FROM security_audit WHERE skill_version_id IN (
                        SELECT id FROM skill_version WHERE skill_id = :skill_id
                    )
                )
                """
            ),
            {"skill_id": skill_id},
        )
        await connection.execute(
            text(
                """
                DELETE FROM security_audit
                WHERE skill_version_id IN (SELECT id FROM skill_version WHERE skill_id = :skill_id)
                """
            ),
            {"skill_id": skill_id},
        )
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

        result = await runtime.consume_once(engine, TimeoutScanner(), count=1, block_ms=100)

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


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_uncommitted_publish_is_requeued_without_spending_scanner_retry(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan-not-ready:{suffix}"
    group_name = f"scan-not-ready-{suffix}"
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    raw_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    publisher_connection = await engine.connect()
    publisher_transaction = await publisher_connection.begin()
    user_id = f"scan-timeout-{suffix}"
    namespace_id = 0
    skill_id = 0
    scanner = SafeScanner()

    try:
        user_id, namespace_id, skill_id, version_id = await _insert_scanning_version(
            publisher_connection,
            suffix,
        )
        await redis_client.xadd(
            stream_key,
            {
                "taskId": f"task-{suffix}",
                "versionId": str(version_id),
                "skillPath": str(tmp_path),
                "retryCount": "0",
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

        before_commit = await runtime.consume_once(engine, scanner, count=1, block_ms=100)
        await publisher_transaction.commit()
        after_commit = await runtime.consume_once(engine, scanner, count=1, block_ms=100)

        async with engine.connect() as connection:
            status = (
                await connection.execute(
                    text("SELECT status FROM skill_version WHERE id = :version_id"),
                    {"version_id": version_id},
                )
            ).scalar_one()

        assert before_commit == ScanConsumerResult(processed=1, acknowledged=1, retried=1)
        assert after_commit == ScanConsumerResult(processed=1, acknowledged=1)
        assert scanner.calls == 1
        assert status == "PENDING_REVIEW"
    finally:
        if publisher_transaction.is_active:
            await publisher_transaction.rollback()
        await publisher_connection.close()
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        if namespace_id and skill_id:
            await _cleanup_scanning_version(
                engine,
                user_id=user_id,
                namespace_id=namespace_id,
                skill_id=skill_id,
            )
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_rolled_back_publish_parks_visibility_requeue_with_real_services(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan-rollback:{suffix}"
    group_name = f"scan-rollback-{suffix}"
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    raw_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    publisher_connection = await engine.connect()
    publisher_transaction = await publisher_connection.begin()
    scanner = SafeScanner()

    try:
        _, _, _, version_id = await _insert_scanning_version(publisher_connection, suffix)
        await redis_client.xadd(
            stream_key,
            {
                "taskId": f"task-{suffix}",
                "versionId": str(version_id),
                "skillPath": str(tmp_path),
                "retryCount": "0",
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
            max_not_ready_requeue_count=1,
        )

        first = await runtime.consume_once(engine, scanner, count=1, block_ms=100)
        await publisher_transaction.rollback()
        second = await runtime.consume_once(engine, scanner, count=1, block_ms=100)
        pending = await raw_redis.xpending(stream_key, group_name)

        assert first == ScanConsumerResult(processed=1, acknowledged=1, retried=1)
        assert second == ScanConsumerResult(processed=1, failed=1)
        assert scanner.calls == 0
        assert pending["pending"] == 1
    finally:
        if publisher_transaction.is_active:
            await publisher_transaction.rollback()
        await publisher_connection.close()
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_publish_commit_after_visibility_limit_is_reconciled_from_pending(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan-late-commit:{suffix}"
    group_name = f"scan-late-commit-{suffix}"
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    raw_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    publisher_connection = await engine.connect()
    publisher_transaction = await publisher_connection.begin()
    user_id = f"scan-timeout-{suffix}"
    namespace_id = 0
    skill_id = 0
    scanner = SafeScanner()

    try:
        user_id, namespace_id, skill_id, version_id = await _insert_scanning_version(
            publisher_connection,
            suffix,
        )
        await redis_client.xadd(
            stream_key,
            {
                "taskId": f"task-{suffix}",
                "versionId": str(version_id),
                "skillPath": str(tmp_path),
                "retryCount": "0",
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
            max_not_ready_requeue_count=0,
        )

        parked = await runtime.consume_once(engine, scanner, count=1, block_ms=100)
        pending_before_commit = await raw_redis.xpending(stream_key, group_name)
        await publisher_transaction.commit()
        reconciled = await runtime.reclaim_once(
            engine,
            scanner,
            min_idle_ms=0,
            count=1,
        )
        pending_after_reconcile = await raw_redis.xpending(stream_key, group_name)

        async with engine.connect() as connection:
            status = (
                await connection.execute(
                    text("SELECT status FROM skill_version WHERE id = :version_id"),
                    {"version_id": version_id},
                )
            ).scalar_one()

        assert parked == ScanConsumerResult(processed=1, failed=1)
        assert pending_before_commit["pending"] == 1
        assert reconciled == ScanConsumerResult(processed=1, acknowledged=1)
        assert pending_after_reconcile["pending"] == 0
        assert scanner.calls == 1
        assert status == "PENDING_REVIEW"
    finally:
        if publisher_transaction.is_active:
            await publisher_transaction.rollback()
        await publisher_connection.close()
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        if namespace_id and skill_id:
            await _cleanup_scanning_version(
                engine,
                user_id=user_id,
                namespace_id=namespace_id,
                skill_id=skill_id,
            )
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_terminal_failure_defers_to_duplicate_worker_holding_real_lease(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    stream_key = f"skillhub:test:scan-terminal-race:{suffix}"
    group_name = f"scan-terminal-race-{suffix}"
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=3, max_overflow=0)
    raw_redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    user_id, namespace_id, skill_id, version_id = await _create_scanning_version(engine, suffix)
    terminal_waiting = asyncio.Event()
    allow_terminal = asyncio.Event()
    duplicate_started = asyncio.Event()
    allow_duplicate = asyncio.Event()
    failed_consumer: asyncio.Task[ScanConsumerResult] | None = None
    duplicate: asyncio.Task[None] | None = None

    class GatedBegin:
        def __init__(self, inner: Any, *, gated: bool) -> None:
            self.inner = inner
            self.gated = gated

        async def __aenter__(self) -> Any:
            if self.gated:
                terminal_waiting.set()
                await allow_terminal.wait()
            return await self.inner.__aenter__()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            return await self.inner.__aexit__(exc_type, exc, tb)

    class GatedEngine:
        def __init__(self) -> None:
            self.begin_count = 0

        def begin(self) -> GatedBegin:
            self.begin_count += 1
            return GatedBegin(engine.begin(), gated=self.begin_count == 2)

    class BlockingSafeScanner:
        async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
            duplicate_started.set()
            await allow_duplicate.wait()
            return SecurityScanResultInput(
                scan_id=f"duplicate-{suffix}",
                verdict="SAFE",
                findings_count=0,
                max_severity=None,
                findings=[],
                scan_duration_seconds=0.01,
                analyzers_requested=["static_analyzer"],
                analyzers_completed=["static_analyzer"],
            )

    try:
        await redis_client.xadd(
            stream_key,
            {
                "taskId": f"task-{suffix}",
                "versionId": str(version_id),
                "skillPath": str(tmp_path),
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
        failed_consumer = asyncio.create_task(
            runtime.consume_once(GatedEngine(), TimeoutScanner(), count=1, block_ms=100)
        )
        await asyncio.wait_for(terminal_waiting.wait(), timeout=5)

        async def run_duplicate() -> None:
            async with engine.begin() as connection:
                await process_scan_task(
                    connection,
                    SecurityScanTask(
                        task_id=f"duplicate-{suffix}",
                        version_id=version_id,
                        skill_path=str(tmp_path),
                    ),
                    BlockingSafeScanner(),
                    storage_base_path=str(tmp_path),
                    scan_temp_dir=str(tmp_path / "scans"),
                )

        duplicate = asyncio.create_task(run_duplicate())
        await asyncio.wait_for(duplicate_started.wait(), timeout=5)
        allow_terminal.set()
        failed_result = await asyncio.wait_for(failed_consumer, timeout=5)
        allow_duplicate.set()
        await asyncio.wait_for(duplicate, timeout=5)
        reclaimed = await runtime.reclaim_once(
            engine,
            SafeScanner(),
            min_idle_ms=0,
            count=1,
        )

        async with engine.connect() as connection:
            status = (
                await connection.execute(
                    text("SELECT status FROM skill_version WHERE id = :version_id"),
                    {"version_id": version_id},
                )
            ).scalar_one()

        assert failed_result == ScanConsumerResult()
        assert reclaimed == ScanConsumerResult(processed=1, acknowledged=1)
        assert status == "PENDING_REVIEW"
    finally:
        allow_terminal.set()
        allow_duplicate.set()
        tasks = [task for task in (failed_consumer, duplicate) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await redis_client.delete(stream_key)
        await redis_client.aclose()
        await _cleanup_scanning_version(
            engine,
            user_id=user_id,
            namespace_id=namespace_id,
            skill_id=skill_id,
        )
        await engine.dispose()


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_scan_task_lease_and_terminal_state_guard_real_postgres(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    user_id, namespace_id, skill_id, version_id = await _create_scanning_version(engine, suffix)
    scanner_started = asyncio.Event()
    scanner_release = asyncio.Event()

    class BlockingScanner:
        async def scan(self, task: SecurityScanTask, skill_path: str) -> SecurityScanResultInput:
            scanner_started.set()
            await scanner_release.wait()
            return SecurityScanResultInput(
                scan_id=f"scan-{suffix}",
                verdict="SAFE",
                findings_count=0,
                max_severity=None,
                findings=[],
                scan_duration_seconds=0.1,
                analyzers_requested=["static_analyzer"],
                analyzers_completed=["static_analyzer"],
            )

    task = SecurityScanTask(task_id=f"task-{suffix}", version_id=version_id, skill_path=str(tmp_path))

    async def run_first_worker() -> None:
        async with engine.begin() as connection:
            await process_scan_task(
                connection,
                task,
                BlockingScanner(),
                storage_base_path=str(tmp_path),
                scan_temp_dir=str(tmp_path / "scans"),
            )

    first_worker = asyncio.create_task(run_first_worker())
    try:
        await asyncio.wait_for(scanner_started.wait(), timeout=5)
        async with engine.begin() as connection:
            with pytest.raises(ScanTaskLeaseUnavailable):
                await process_scan_task(
                    connection,
                    task,
                    BlockingScanner(),
                    storage_base_path=str(tmp_path),
                    scan_temp_dir=str(tmp_path / "scans"),
                )

        scanner_release.set()
        await asyncio.wait_for(first_worker, timeout=5)

        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE skill_version SET status = 'PUBLISHED' WHERE id = :version_id"),
                {"version_id": version_id},
            )
            before = (
                await connection.execute(
                    text(
                        """
                        SELECT sa.scan_id, le.scan_status
                        FROM security_audit sa
                        LEFT JOIN local_security_scan_execution le ON le.security_audit_id = sa.id
                        WHERE sa.skill_version_id = :version_id
                        """
                    ),
                    {"version_id": version_id},
                )
            ).mappings().one()
            applied = await apply_security_scan_result(
                connection,
                version_id=version_id,
                scanner_type="skill-scanner",
                scan_result=SecurityScanResultInput("late-result", "DANGEROUS", 1, "HIGH", [], 0.2),
            )
            after = (
                await connection.execute(
                    text(
                        """
                        SELECT sv.status, sa.scan_id, le.scan_status
                        FROM skill_version sv
                        JOIN security_audit sa ON sa.skill_version_id = sv.id
                        LEFT JOIN local_security_scan_execution le ON le.security_audit_id = sa.id
                        WHERE sv.id = :version_id
                        """
                    ),
                    {"version_id": version_id},
                )
            ).mappings().one()

        assert applied.status_changed is False
        assert applied.new_status == "PUBLISHED"
        assert after["status"] == "PUBLISHED"
        assert after["scan_id"] == before["scan_id"]
        assert after["scan_status"] == before["scan_status"]
    finally:
        scanner_release.set()
        if not first_worker.done():
            await first_worker
        await _cleanup_scanning_version(
            engine,
            user_id=user_id,
            namespace_id=namespace_id,
            skill_id=skill_id,
        )
        await engine.dispose()
