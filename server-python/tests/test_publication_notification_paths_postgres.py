from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.promotion.workflow import (
    PromotionApproveInput,
    PromotionSubmitInput,
    approve_promotion,
    submit_promotion,
)
from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata
from app.review.approval import ReviewApproveInput, approve_review_task

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@dataclass(frozen=True)
class PublicationFixture:
    owner_id: str
    reviewer_id: str
    subscriber_id: str
    disabled_subscriber_id: str
    namespace_id: int
    namespace: str
    slug: str


class RecordingFanout:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.published.append((user_id, payload))


async def _create_fixture(engine: AsyncEngine) -> PublicationFixture:
    suffix = uuid4().hex[:12]
    owner_id = f"publication-owner-{suffix}"
    reviewer_id = f"publication-reviewer-{suffix}"
    subscriber_id = f"publication-subscriber-{suffix}"
    disabled_subscriber_id = f"publication-disabled-{suffix}"
    namespace = f"publication-{suffix}"
    slug = f"publication-{suffix}"
    users = [
        (owner_id, "Publication owner"),
        (reviewer_id, "Publication reviewer"),
        (subscriber_id, "Publication subscriber"),
        (disabled_subscriber_id, "Publication disabled subscriber"),
    ]
    async with engine.begin() as connection:
        for user_id, display_name in users:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"
                ),
                {"user_id": user_id, "display_name": display_name},
            )
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, status, created_by)
                        VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :owner_id)
                        RETURNING id
                        """
                    ),
                    {"slug": namespace, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :reviewer_id, 'ADMIN')
                """
            ),
            {"namespace_id": namespace_id, "reviewer_id": reviewer_id},
        )
        await connection.execute(
            text(
                """
                INSERT INTO user_role_binding (user_id, role_id)
                SELECT :reviewer_id, id FROM role WHERE code = 'SKILL_ADMIN'
                """
            ),
            {"reviewer_id": reviewer_id},
        )
    return PublicationFixture(
        owner_id=owner_id,
        reviewer_id=reviewer_id,
        subscriber_id=subscriber_id,
        disabled_subscriber_id=disabled_subscriber_id,
        namespace_id=namespace_id,
        namespace=namespace,
        slug=slug,
    )


def _publish_input(
    tmp_path: Any,
    fixture: PublicationFixture,
    *,
    version: str,
    auto_publish: bool,
    visibility: str = "PUBLIC",
) -> PublishWriteInput:
    return PublishWriteInput(
        namespace_id=fixture.namespace_id,
        namespace_slug=fixture.namespace,
        slug=fixture.slug,
        display_name="Publication Skill",
        summary="Publication notification integration",
        publisher_id=fixture.owner_id,
        visibility=visibility,
        version=version,
        auto_publish=auto_publish,
        metadata=SkillMetadata(
            name="Publication Skill",
            description="Publication notification integration",
            version=version,
            frontmatter={
                "name": "Publication Skill",
                "description": "Publication notification integration",
                "version": version,
            },
        ),
        entries=[
            PackageEntry(
                "SKILL.md",
                f"# Publication Skill {version}\n".encode(),
                "text/markdown",
            )
        ],
        storage_base_path=str(tmp_path),
        scanner_enabled=False,
        now=datetime.now(UTC),
    )


async def _notification_rows(
    engine: AsyncEngine,
    *,
    skill_id: int,
    version_id: int,
) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT recipient_id, category, event_type,
                               CAST(body_json AS JSONB) ->> 'versionId' AS version_id
                        FROM notification
                        WHERE entity_type = 'SKILL'
                          AND entity_id = :skill_id
                          AND CAST(body_json AS JSONB) ->> 'versionId' = :version_id
                        ORDER BY category, event_type, recipient_id
                        """
                    ),
                    {"skill_id": skill_id, "version_id": str(version_id)},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


async def _cleanup_fixture(engine: AsyncEngine, fixture: PublicationFixture) -> None:
    user_ids = [
        fixture.owner_id,
        fixture.reviewer_id,
        fixture.subscriber_id,
        fixture.disabled_subscriber_id,
    ]
    async with engine.begin() as connection:
        source_skill_ids = list(
            (
                await connection.execute(
                    text("SELECT id FROM skill WHERE namespace_id = :namespace_id"),
                    {"namespace_id": fixture.namespace_id},
                )
            ).scalars().all()
        )
        target_skill_ids = list(
            (
                await connection.execute(
                    text(
                        """
                        SELECT id FROM skill
                        WHERE source_skill_id = ANY(CAST(:source_skill_ids AS bigint[]))
                        """
                    ),
                    {"source_skill_ids": source_skill_ids or [-1]},
                )
            ).scalars().all()
        )
        skill_ids = source_skill_ids + target_skill_ids
        version_ids = list(
            (
                await connection.execute(
                    text(
                        "SELECT id FROM skill_version WHERE skill_id = ANY(CAST(:skill_ids AS bigint[]))"
                    ),
                    {"skill_ids": skill_ids or [-1]},
                )
            ).scalars().all()
        )
        await connection.execute(
            text("DELETE FROM notification WHERE recipient_id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )
        await connection.execute(
            text("DELETE FROM user_notification WHERE user_id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )
        await connection.execute(
            text("DELETE FROM promotion_request WHERE source_skill_id = ANY(CAST(:skill_ids AS bigint[]))"),
            {"skill_ids": source_skill_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM review_task WHERE skill_version_id = ANY(CAST(:version_ids AS bigint[]))"),
            {"version_ids": version_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM audit_log WHERE actor_user_id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )
        await connection.execute(
            text("DELETE FROM skill_subscription WHERE skill_id = ANY(CAST(:skill_ids AS bigint[]))"),
            {"skill_ids": skill_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM skill_search_document WHERE skill_id = ANY(CAST(:skill_ids AS bigint[]))"),
            {"skill_ids": skill_ids or [-1]},
        )
        await connection.execute(
            text("UPDATE skill SET latest_version_id = NULL WHERE id = ANY(CAST(:skill_ids AS bigint[]))"),
            {"skill_ids": skill_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM skill_file WHERE version_id = ANY(CAST(:version_ids AS bigint[]))"),
            {"version_ids": version_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM skill_version WHERE id = ANY(CAST(:version_ids AS bigint[]))"),
            {"version_ids": version_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM skill WHERE id = ANY(CAST(:target_skill_ids AS bigint[]))"),
            {"target_skill_ids": target_skill_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM skill WHERE id = ANY(CAST(:source_skill_ids AS bigint[]))"),
            {"source_skill_ids": source_skill_ids or [-1]},
        )
        await connection.execute(
            text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM namespace WHERE id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM notification_preference WHERE user_id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )
        await connection.execute(
            text("DELETE FROM user_role_binding WHERE user_id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )
        await connection.execute(
            text("DELETE FROM user_account WHERE id = ANY(CAST(:user_ids AS varchar[]))"),
            {"user_ids": user_ids},
        )


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_auto_publish_and_review_approval_notify_eligible_subscribers_in_postgres(
    tmp_path,
) -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=3, max_overflow=0)
    fixture = await _create_fixture(engine)
    try:
        initial = await execute_publish_write(
            engine,
            _publish_input(tmp_path, fixture, version="1.0.0", auto_publish=True),
        )
        async with engine.begin() as connection:
            for user_id in (
                fixture.owner_id,
                fixture.subscriber_id,
                fixture.disabled_subscriber_id,
            ):
                await connection.execute(
                    text(
                        "INSERT INTO skill_subscription (skill_id, user_id) VALUES (:skill_id, :user_id)"
                    ),
                    {"skill_id": initial.skill_id, "user_id": user_id},
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO notification_preference (user_id, category, channel, enabled)
                    VALUES (:user_id, 'PUBLISH', 'IN_APP', FALSE)
                    """
                ),
                {"user_id": fixture.disabled_subscriber_id},
            )
            await connection.execute(
                text("DELETE FROM notification WHERE recipient_id = ANY(CAST(:user_ids AS varchar[]))"),
                {
                    "user_ids": [
                        fixture.owner_id,
                        fixture.reviewer_id,
                        fixture.subscriber_id,
                        fixture.disabled_subscriber_id,
                    ]
                },
            )

        auto_fanout = RecordingFanout()
        auto_published = await execute_publish_write(
            engine,
            _publish_input(tmp_path, fixture, version="1.1.0", auto_publish=True),
            notification_fanout=auto_fanout,
        )
        auto_rows = await _notification_rows(
            engine,
            skill_id=auto_published.skill_id,
            version_id=auto_published.version_id,
        )
        assert [
            (str(row["recipient_id"]), str(row["event_type"])) for row in auto_rows
        ] == sorted(
            [
                (fixture.owner_id, "SKILL_PUBLISHED"),
                (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
            ]
        )
        assert sorted(user_id for user_id, _payload in auto_fanout.published) == sorted(
            [fixture.owner_id, fixture.subscriber_id]
        )

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO skill_subscription (skill_id, user_id) VALUES (:skill_id, :user_id)"
                ),
                {"skill_id": initial.skill_id, "user_id": fixture.reviewer_id},
            )
        submitted = await execute_publish_write(
            engine,
            _publish_input(tmp_path, fixture, version="1.2.0", auto_publish=False),
        )
        assert submitted.version_status == "PENDING_REVIEW"
        assert submitted.side_effects.review_task_id is not None
        assert await _notification_rows(
            engine,
            skill_id=submitted.skill_id,
            version_id=submitted.version_id,
        ) == []

        review_fanout = RecordingFanout()
        approved = await approve_review_task(
            engine,
            ReviewApproveInput(
                review_task_id=int(submitted.side_effects.review_task_id),
                reviewer_id=fixture.reviewer_id,
                comment="approved in PostgreSQL integration",
                now=datetime.now(UTC),
            ),
            notification_fanout=review_fanout,
        )
        assert approved["status"] == "APPROVED"
        review_rows = await _notification_rows(
            engine,
            skill_id=submitted.skill_id,
            version_id=submitted.version_id,
        )
        publish_rows = [row for row in review_rows if row["category"] == "PUBLISH"]
        assert [
            (str(row["recipient_id"]), str(row["event_type"]))
            for row in publish_rows
        ] == sorted(
            [
                (fixture.owner_id, "SUBSCRIPTION_NEW_VERSION"),
                (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
            ]
        )
        assert fixture.reviewer_id not in {
            str(row["recipient_id"]) for row in publish_rows
        }
        assert fixture.disabled_subscriber_id not in {
            str(row["recipient_id"]) for row in publish_rows
        }
        fanout_publish_recipients = {
            user_id
            for user_id, payload in review_fanout.published
            if payload["category"] == "PUBLISH"
        }
        assert fanout_publish_recipients == {
            fixture.owner_id,
            fixture.subscriber_id,
        }

        async def force_rollback(
            _connection: Any,
            _skill_id: int,
            _version_id: int,
        ) -> None:
            raise RuntimeError("forced auto-publish rollback")

        rollback_fanout = RecordingFanout()
        with pytest.raises(RuntimeError, match="forced auto-publish rollback"):
            await execute_publish_write(
                engine,
                _publish_input(tmp_path, fixture, version="1.3.0", auto_publish=True),
                notification_fanout=rollback_fanout,
                after_publish=force_rollback,
            )
        async with engine.connect() as connection:
            rolled_back_versions = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM skill_version WHERE skill_id = :skill_id AND version = '1.3.0'"
                        ),
                        {"skill_id": initial.skill_id},
                    )
                ).scalar_one()
            )
        assert rolled_back_versions == 0
        assert rollback_fanout.published == []
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_publication_notifications_recheck_current_access_in_postgres(
    tmp_path,
) -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=3, max_overflow=0)
    fixture = await _create_fixture(engine)
    try:
        initial = await execute_publish_write(
            engine,
            _publish_input(tmp_path, fixture, version="1.0.0", auto_publish=True),
        )
        async with engine.begin() as connection:
            for user_id in (
                fixture.reviewer_id,
                fixture.subscriber_id,
                fixture.disabled_subscriber_id,
            ):
                await connection.execute(
                    text(
                        "INSERT INTO skill_subscription (skill_id, user_id) VALUES (:skill_id, :user_id)"
                    ),
                    {"skill_id": initial.skill_id, "user_id": user_id},
                )
            for user_id in (
                fixture.subscriber_id,
                fixture.disabled_subscriber_id,
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace_member (namespace_id, user_id, role)
                        VALUES (:namespace_id, :user_id, 'MEMBER')
                        """
                    ),
                    {"namespace_id": fixture.namespace_id, "user_id": user_id},
                )
            await connection.execute(
                text("UPDATE user_account SET status = 'DISABLED' WHERE id = :user_id"),
                {"user_id": fixture.disabled_subscriber_id},
            )

        active_namespace = await execute_publish_write(
            engine,
            _publish_input(
                tmp_path,
                fixture,
                version="1.1.0",
                auto_publish=True,
                visibility="NAMESPACE_ONLY",
            ),
        )
        active_rows = await _notification_rows(
            engine,
            skill_id=active_namespace.skill_id,
            version_id=active_namespace.version_id,
        )
        assert {
            (str(row["recipient_id"]), str(row["event_type"]))
            for row in active_rows
        } == {
            (fixture.owner_id, "SKILL_PUBLISHED"),
            (fixture.reviewer_id, "SUBSCRIPTION_NEW_VERSION"),
            (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
        }

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM namespace_member
                    WHERE namespace_id = :namespace_id
                      AND user_id = :user_id
                    """
                ),
                {
                    "namespace_id": fixture.namespace_id,
                    "user_id": fixture.subscriber_id,
                },
            )

        removed_member = await execute_publish_write(
            engine,
            _publish_input(
                tmp_path,
                fixture,
                version="1.2.0",
                auto_publish=True,
                visibility="NAMESPACE_ONLY",
            ),
        )
        removed_rows = await _notification_rows(
            engine,
            skill_id=removed_member.skill_id,
            version_id=removed_member.version_id,
        )
        assert {
            (str(row["recipient_id"]), str(row["event_type"]))
            for row in removed_rows
        } == {
            (fixture.owner_id, "SKILL_PUBLISHED"),
            (fixture.reviewer_id, "SUBSCRIPTION_NEW_VERSION"),
        }

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES (:namespace_id, :user_id, 'MEMBER')
                    """
                ),
                {
                    "namespace_id": fixture.namespace_id,
                    "user_id": fixture.subscriber_id,
                },
            )
            await connection.execute(
                text("UPDATE namespace SET status = 'ARCHIVED' WHERE id = :namespace_id"),
                {"namespace_id": fixture.namespace_id},
            )

        archived_namespace = await execute_publish_write(
            engine,
            _publish_input(
                tmp_path,
                fixture,
                version="1.3.0",
                auto_publish=True,
                visibility="NAMESPACE_ONLY",
            ),
        )
        archived_rows = await _notification_rows(
            engine,
            skill_id=archived_namespace.skill_id,
            version_id=archived_namespace.version_id,
        )
        assert {
            (str(row["recipient_id"]), str(row["event_type"]))
            for row in archived_rows
        } == {
            (fixture.owner_id, "SKILL_PUBLISHED"),
            (fixture.reviewer_id, "SUBSCRIPTION_NEW_VERSION"),
        }
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_promotion_materialization_applies_publication_contract_in_postgres(
    tmp_path,
) -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=3, max_overflow=0)
    fixture = await _create_fixture(engine)
    try:
        source = await execute_publish_write(
            engine,
            _publish_input(tmp_path, fixture, version="1.0.0", auto_publish=True),
        )
        async with engine.connect() as connection:
            global_namespace_id = int(
                (
                    await connection.execute(
                        text("SELECT id FROM namespace WHERE slug = 'global' AND type = 'GLOBAL'")
                    )
                ).scalar_one()
            )
        submitted = await submit_promotion(
            engine,
            PromotionSubmitInput(
                source_skill_id=source.skill_id,
                source_version_id=source.version_id,
                target_namespace_id=global_namespace_id,
                user_id=fixture.owner_id,
                now=datetime.now(UTC),
            ),
        )
        fanout = RecordingFanout()
        approved = await approve_promotion(
            engine,
            PromotionApproveInput(
                promotion_id=int(submitted["id"]),
                reviewer_id=fixture.reviewer_id,
                comment="promote in PostgreSQL integration",
                now=datetime.now(UTC),
            ),
            notification_fanout=fanout,
        )
        target_skill_id = int(approved["targetSkillId"])
        async with engine.connect() as connection:
            target_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT s.source_skill_id, sv.status
                            FROM skill s
                            JOIN skill_version sv ON sv.id = s.latest_version_id
                            WHERE s.id = :target_skill_id
                            """
                        ),
                        {"target_skill_id": target_skill_id},
                    )
                )
                .mappings()
                .one()
            )
            search_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM skill_search_document WHERE skill_id = :target_skill_id"
                        ),
                        {"target_skill_id": target_skill_id},
                    )
                ).scalar_one()
            )
            publish_notification_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM notification
                            WHERE entity_type = 'SKILL'
                              AND entity_id = :target_skill_id
                              AND category = 'PUBLISH'
                            """
                        ),
                        {"target_skill_id": target_skill_id},
                    )
                ).scalar_one()
            )
        assert int(target_row["source_skill_id"]) == source.skill_id
        assert str(target_row["status"]) == "PUBLISHED"
        assert search_count == 1
        assert publish_notification_count == 0
        assert fanout.published == []
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()
