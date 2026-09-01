from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.redis import SkillHubRedisClient
from app.publish.orchestration import (
    PublishWriteInput,
    execute_publish_write,
)
from app.publish.package import PackageEntry, SkillMetadata
from app.publish.scan_contracts import ScanTaskPayload
from app.publish.scan_outbox import ScanOutboxDispatcher, ScanTaskPublisher
from app.publish.scanner_handoff import RedisScanTaskPublisher

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")


@dataclass(frozen=True)
class PublishObservation:
    version_id: int
    version_status: str
    security_audit_count: int


class ObservingScanTaskPublisher:
    def __init__(
        self,
        engine: AsyncEngine,
        delegate: ScanTaskPublisher,
    ) -> None:
        self.engine = engine
        self.delegate = delegate
        self.observations: list[PublishObservation] = []

    async def publish_scan_task(self, task: ScanTaskPayload) -> None:
        async with self.engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT version.status,
                               COUNT(audit.id) AS security_audit_count
                        FROM skill_version version
                        LEFT JOIN security_audit audit
                          ON audit.skill_version_id = version.id
                         AND audit.scanner_type = 'SKILL_SCANNER'
                         AND audit.deleted_at IS NULL
                        WHERE version.id = :version_id
                        GROUP BY version.status
                        """
                    ),
                    {"version_id": task.version_id},
                )
            ).mappings().one_or_none()
        if row is None:
            raise AssertionError(
                f"Scan task published before version {task.version_id} was visible"
            )
        self.observations.append(
            PublishObservation(
                version_id=task.version_id,
                version_status=str(row["status"]),
                security_audit_count=int(row["security_audit_count"]),
            )
        )
        await self.delegate.publish_scan_task(task)


def publish_input(
    tmp_path: Any,
    *,
    namespace_id: int,
    publisher_id: str,
    slug: str,
    task_id: str,
) -> PublishWriteInput:
    return PublishWriteInput(
        namespace_id=namespace_id,
        namespace_slug=f"scan-transaction-{namespace_id}",
        slug=slug,
        display_name=slug,
        summary="Post-commit scan publication integration",
        publisher_id=publisher_id,
        visibility="PRIVATE",
        version="1.0.0",
        auto_publish=False,
        metadata=SkillMetadata(
            name=slug,
            description="Post-commit scan publication integration",
            version="1.0.0",
            frontmatter={
                "name": slug,
                "description": "Post-commit scan publication integration",
                "version": "1.0.0",
            },
        ),
        entries=[PackageEntry("SKILL.md", f"# {slug}\n".encode(), "text/markdown")],
        storage_base_path=str(tmp_path),
        scanner_enabled=True,
        scan_mode="upload",
        task_id=task_id,
    )


@pytest.mark.skipif(
    TEST_DATABASE_URL is None or TEST_REDIS_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL and SKILLHUB_TEST_REDIS_URL",
)
@pytest.mark.anyio
async def test_scan_task_is_visible_once_after_commit_and_absent_on_rollback(
    tmp_path,
) -> None:
    suffix = uuid4().hex[:12]
    user_id = f"scan-publish-{suffix}"
    namespace_slug = f"scan-publish-{suffix}"
    committed_stream = f"skillhub:test:scan-publish-commit:{suffix}"
    rolled_back_stream = f"skillhub:test:scan-publish-rollback:{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=3, max_overflow=0)
    raw_redis = Redis.from_url(str(TEST_REDIS_URL), decode_responses=True)
    redis_client = SkillHubRedisClient(raw_redis)
    namespace_id: int | None = None

    try:
        await redis_client.delete(committed_stream, rolled_back_stream)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES (:user_id, 'Scan publish integration')
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
                            VALUES (
                                :slug, :slug, 'TEAM', 'ACTIVE', :user_id
                            )
                            RETURNING id
                            """
                        ),
                        {"slug": namespace_slug, "user_id": user_id},
                    )
                ).scalar_one()
            )

        committed_publisher = ObservingScanTaskPublisher(
            engine,
            RedisScanTaskPublisher(redis_client, committed_stream),
        )
        committed = await execute_publish_write(
            engine,
            publish_input(
                tmp_path,
                namespace_id=namespace_id,
                publisher_id=user_id,
                slug=f"committed-{suffix}",
                task_id=f"committed-task-{suffix}",
            ),
        )

        async with engine.connect() as connection:
            committed_outbox = (
                await connection.execute(
                    text(
                        """
                        SELECT task_id, version_id, status, retry_count
                        FROM scan_task_outbox
                        WHERE task_id = :task_id
                        """
                    ),
                    {"task_id": f"committed-task-{suffix}"},
                )
            ).mappings().one()

        assert dict(committed_outbox) == {
            "task_id": f"committed-task-{suffix}",
            "version_id": committed.version_id,
            "status": "PENDING",
            "retry_count": 0,
        }
        assert committed_publisher.observations == []
        assert await raw_redis.xlen(committed_stream) == 0

        dispatched = await ScanOutboxDispatcher(
            engine,
            committed_publisher,
        ).dispatch_once()
        committed_messages = await raw_redis.xrange(committed_stream)
        assert dispatched.claimed == 1
        assert dispatched.sent == 1
        assert committed_publisher.observations == [
            PublishObservation(
                version_id=committed.version_id,
                version_status="SCANNING",
                security_audit_count=1,
            )
        ]
        assert len(committed_messages) == 1
        assert committed_messages[0][1]["taskId"] == f"committed-task-{suffix}"
        assert committed_messages[0][1]["versionId"] == str(committed.version_id)

        rolled_back_publisher = ObservingScanTaskPublisher(
            engine,
            RedisScanTaskPublisher(redis_client, rolled_back_stream),
        )

        async def fail_transaction(
            _connection: Any,
            _skill_id: int,
            _version_id: int,
        ) -> None:
            raise RuntimeError("forced publish rollback")

        with pytest.raises(RuntimeError, match="forced publish rollback"):
            await execute_publish_write(
                engine,
                publish_input(
                    tmp_path,
                    namespace_id=namespace_id,
                    publisher_id=user_id,
                    slug=f"rolled-back-{suffix}",
                task_id=f"rolled-back-task-{suffix}",
            ),
                after_publish=fail_transaction,
            )

        assert rolled_back_publisher.observations == []
        assert await raw_redis.xlen(rolled_back_stream) == 0
        async with engine.connect() as connection:
            rolled_back_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM skill
                            WHERE namespace_id = :namespace_id
                              AND slug = :slug
                            """
                        ),
                        {
                            "namespace_id": namespace_id,
                            "slug": f"rolled-back-{suffix}",
                        },
                    )
                ).scalar_one()
            )
            rolled_back_outbox_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM scan_task_outbox
                            WHERE task_id = :task_id
                            """
                        ),
                        {"task_id": f"rolled-back-task-{suffix}"},
                    )
                ).scalar_one()
            )
        assert rolled_back_count == 0
        assert rolled_back_outbox_count == 0
    finally:
        await redis_client.delete(committed_stream, rolled_back_stream)
        await redis_client.aclose()
        async with engine.begin() as connection:
            if namespace_id is not None:
                skill_ids = list(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id
                                FROM skill
                                WHERE namespace_id = :namespace_id
                                """
                            ),
                            {"namespace_id": namespace_id},
                        )
                    ).scalars().all()
                )
                version_ids = list(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT version.id
                                FROM skill_version version
                                JOIN skill ON skill.id = version.skill_id
                                WHERE skill.namespace_id = :namespace_id
                                """
                            ),
                            {"namespace_id": namespace_id},
                        )
                    ).scalars().all()
                )
                await connection.execute(
                    text(
                        """
                        DELETE FROM scan_task_outbox
                        WHERE publisher_id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                )
                if skill_ids:
                    await connection.execute(
                        text(
                            """
                            UPDATE skill
                            SET latest_version_id = NULL
                            WHERE id = ANY(:skill_ids)
                            """
                        ),
                        {"skill_ids": skill_ids},
                    )
                    await connection.execute(
                        text(
                            "DELETE FROM skill_search_document WHERE skill_id = ANY(:skill_ids)"
                        ),
                        {"skill_ids": skill_ids},
                    )
                if version_ids:
                    await connection.execute(
                        text(
                            """
                            DELETE FROM local_security_scan_execution
                            WHERE security_audit_id IN (
                                SELECT id
                                FROM security_audit
                                WHERE skill_version_id = ANY(:version_ids)
                            )
                            """
                        ),
                        {"version_ids": version_ids},
                    )
                    await connection.execute(
                        text(
                            "DELETE FROM security_audit WHERE skill_version_id = ANY(:version_ids)"
                        ),
                        {"version_ids": version_ids},
                    )
                    await connection.execute(
                        text(
                            "DELETE FROM skill_file WHERE version_id = ANY(:version_ids)"
                        ),
                        {"version_ids": version_ids},
                    )
                    await connection.execute(
                        text("DELETE FROM skill_version WHERE id = ANY(:version_ids)"),
                        {"version_ids": version_ids},
                    )
                if skill_ids:
                    await connection.execute(
                        text("DELETE FROM skill WHERE id = ANY(:skill_ids)"),
                        {"skill_ids": skill_ids},
                    )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :user_id"),
                {"user_id": user_id},
            )
        await engine.dispose()
