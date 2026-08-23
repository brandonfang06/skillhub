from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.lifecycle import skill as lifecycle_skill
from app.lifecycle.skill import SkillConfirmPublishInput, confirm_publish_skill_version

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@dataclass(frozen=True)
class ConfirmPublishFixture:
    owner_id: str
    admin_id: str
    subscriber_id: str
    disabled_subscriber_id: str
    namespace_id: int
    namespace: str
    skill_id: int
    slug: str
    version_id: int


class RecordingFanout:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.published.append((user_id, payload))


class FailingFanout:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.attempts += 1
        raise RuntimeError("SSE connection failed")


async def _create_fixture(engine: AsyncEngine) -> ConfirmPublishFixture:
    suffix = uuid4().hex[:12]
    owner_id = f"confirm-owner-{suffix}"
    admin_id = f"confirm-admin-{suffix}"
    subscriber_id = f"confirm-subscriber-{suffix}"
    disabled_subscriber_id = f"confirm-disabled-{suffix}"
    namespace = f"confirm-{suffix}"
    slug = f"confirm-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"
            ),
            {"user_id": owner_id, "display_name": "Confirm owner"},
        )
        await connection.execute(
            text(
                "INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"
            ),
            {"user_id": admin_id, "display_name": "Confirm admin"},
        )
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, created_by)
                        VALUES (:slug, :display_name, 'TEAM', :owner_id)
                        RETURNING id
                        """
                    ),
                    {
                        "slug": namespace,
                        "display_name": namespace,
                        "owner_id": owner_id,
                    },
                )
            ).scalar_one()
        )
        skill_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill (
                            namespace_id, slug, display_name, summary, owner_id,
                            visibility, created_by, updated_by
                        )
                        VALUES (
                            :namespace_id, :slug, 'Confirm Skill', 'Confirm publication outcomes',
                            :owner_id, 'PRIVATE', :owner_id, :owner_id
                        )
                        RETURNING id
                        """
                    ),
                    {"namespace_id": namespace_id, "slug": slug, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :admin_id, 'ADMIN')
                """
            ),
            {"namespace_id": namespace_id, "admin_id": admin_id},
        )
        version_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_version (
                            skill_id, version, status, parsed_metadata_json, file_count,
                            total_size, created_by
                        )
                        VALUES (
                            :skill_id, '1.1.0', 'UPLOADED', CAST(:metadata AS jsonb), 1,
                            10, :owner_id
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "skill_id": skill_id,
                        "metadata": '{"name":"Confirm Skill","description":"Confirm publication outcomes","version":"1.1.0"}',
                        "owner_id": owner_id,
                    },
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO skill_file (
                    version_id, file_path, file_size, content_type, sha256, storage_key
                )
                VALUES (
                    :version_id, 'SKILL.md', 10, 'text/markdown', :sha256, :storage_key
                )
                """
            ),
            {
                "version_id": version_id,
                "sha256": "a" * 64,
                "storage_key": f"skills/{skill_id}/{version_id}/SKILL.md",
            },
        )
        for user_id in (owner_id, subscriber_id, disabled_subscriber_id):
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_subscription (skill_id, user_id)
                    VALUES (:skill_id, :user_id)
                    """
                ),
                {"skill_id": skill_id, "user_id": user_id},
            )
        await connection.execute(
            text(
                """
                INSERT INTO notification_preference (user_id, category, channel, enabled)
                VALUES (:user_id, 'PUBLISH', 'IN_APP', FALSE)
                """
            ),
            {"user_id": disabled_subscriber_id},
        )
    return ConfirmPublishFixture(
        owner_id=owner_id,
        admin_id=admin_id,
        subscriber_id=subscriber_id,
        disabled_subscriber_id=disabled_subscriber_id,
        namespace_id=namespace_id,
        namespace=namespace,
        skill_id=skill_id,
        slug=slug,
        version_id=version_id,
    )


async def _cleanup_fixture(engine: AsyncEngine, fixture: ConfirmPublishFixture) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "DELETE FROM notification WHERE entity_type = 'SKILL' AND entity_id = :skill_id"
            ),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text("DELETE FROM notification_preference WHERE user_id = :user_id"),
            {"user_id": fixture.disabled_subscriber_id},
        )
        await connection.execute(
            text("DELETE FROM skill_subscription WHERE skill_id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text("DELETE FROM skill_search_document WHERE skill_id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text(
                "DELETE FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = :version_id"
            ),
            {"version_id": fixture.version_id},
        )
        await connection.execute(
            text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(
            text("DELETE FROM skill_file WHERE version_id = :version_id"),
            {"version_id": fixture.version_id},
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
            text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM namespace WHERE id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM user_account WHERE id = :owner_id"),
            {"owner_id": fixture.owner_id},
        )
        await connection.execute(
            text("DELETE FROM user_account WHERE id = :admin_id"),
            {"admin_id": fixture.admin_id},
        )


def _confirm_input(
    fixture: ConfirmPublishFixture,
    *,
    actor_id: str | None = None,
    now: datetime | None = None,
) -> SkillConfirmPublishInput:
    return SkillConfirmPublishInput(
        namespace=fixture.namespace,
        slug=fixture.slug,
        version="1.1.0",
        user_id=actor_id or fixture.owner_id,
        request_id=f"confirm-{fixture.version_id}",
        now=now or datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_confirm_publish_postgres_commits_search_and_notifications_once_across_replay() -> (
    None
):
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(engine)
    fanout = RecordingFanout()
    try:
        first = await confirm_publish_skill_version(
            engine, _confirm_input(fixture), notification_fanout=fanout
        )
        replay = await confirm_publish_skill_version(
            engine,
            _confirm_input(fixture, actor_id=fixture.admin_id),
            notification_fanout=fanout,
        )

        async with engine.connect() as connection:
            version_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT sv.status, s.latest_version_id
                        FROM skill_version sv
                        JOIN skill s ON s.id = sv.skill_id
                        WHERE sv.id = :version_id
                        """
                        ),
                        {"version_id": fixture.version_id},
                    )
                )
                .mappings()
                .one()
            )
            audit_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM audit_log
                            WHERE action = 'CONFIRM_PUBLISH'
                              AND target_type = 'SKILL_VERSION'
                              AND target_id = :version_id
                            """
                        ),
                        {"version_id": fixture.version_id},
                    )
                ).scalar_one()
            )
            search_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM skill_search_document WHERE skill_id = :skill_id"
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )
            notifications = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT recipient_id, event_type
                        FROM notification
                        WHERE entity_type = 'SKILL'
                          AND entity_id = :skill_id
                          AND category = 'PUBLISH'
                        ORDER BY recipient_id
                        """
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                )
                .mappings()
                .all()
            )
            audit_actors = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT actor_user_id
                            FROM audit_log
                            WHERE action = 'CONFIRM_PUBLISH'
                              AND target_type = 'SKILL_VERSION'
                              AND target_id = :version_id
                            ORDER BY created_at ASC, id ASC
                            """
                        ),
                        {"version_id": fixture.version_id},
                    )
                )
                .scalars()
                .all()
            )

        assert first == replay
        assert version_row["status"] == "PUBLISHED"
        assert int(version_row["latest_version_id"]) == fixture.version_id
        assert audit_count == 1
        assert list(audit_actors) == [fixture.owner_id]
        assert search_count == 1
        assert [
            (str(row["recipient_id"]), str(row["event_type"])) for row in notifications
        ] == sorted(
            [
                (fixture.owner_id, "SKILL_PUBLISHED"),
                (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
            ]
        )
        assert [user_id for user_id, _payload in fanout.published] == [
            fixture.owner_id,
            fixture.subscriber_id,
        ]
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_concurrent_confirm_publish_postgres_creates_one_audit_and_one_notification_per_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=0)
    fixture = await _create_fixture(engine)
    fanout = RecordingFanout()
    first_locked = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    original_reader = lifecycle_skill._read_skill_context
    reader_calls = 0

    async def paused_reader(
        connection: object,
        namespace: str,
        slug: str,
        *,
        lock_skill: bool = False,
    ) -> dict[str, Any]:
        nonlocal reader_calls
        reader_calls += 1
        call_number = reader_calls
        if call_number == 2:
            second_started.set()
        row = await original_reader(
            connection,
            namespace,
            slug,
            lock_skill=lock_skill,
        )
        if call_number == 1:
            first_locked.set()
            await release_first.wait()
        return row

    monkeypatch.setattr(lifecycle_skill, "_read_skill_context", paused_reader)
    first_time = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    replay_time = datetime(2026, 8, 23, 13, 0, tzinfo=UTC)
    try:
        first_task = asyncio.create_task(
            confirm_publish_skill_version(
                engine,
                _confirm_input(fixture, now=first_time),
                notification_fanout=fanout,
            )
        )
        await asyncio.wait_for(first_locked.wait(), timeout=5)
        replay_task = asyncio.create_task(
            confirm_publish_skill_version(
                engine,
                _confirm_input(
                    fixture,
                    actor_id=fixture.admin_id,
                    now=replay_time,
                ),
                notification_fanout=fanout,
            )
        )
        await asyncio.wait_for(second_started.wait(), timeout=5)
        await asyncio.sleep(0.05)
        release_first.set()
        first_result, replay_result = await asyncio.gather(first_task, replay_task)

        async with engine.connect() as connection:
            audit_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM audit_log
                            WHERE action = 'CONFIRM_PUBLISH'
                              AND target_type = 'SKILL_VERSION'
                              AND target_id = :version_id
                            """
                        ),
                        {"version_id": fixture.version_id},
                    )
                ).scalar_one()
            )
            notifications = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT recipient_id, event_type, created_at,
                                   CAST(body_json AS JSONB) ->> 'versionId' AS version_id
                            FROM notification
                            WHERE entity_type = 'SKILL'
                              AND entity_id = :skill_id
                              AND category = 'PUBLISH'
                            ORDER BY recipient_id
                            """
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                )
                .mappings()
                .all()
            )

        assert first_result == replay_result
        assert audit_count == 1
        assert [
            (
                str(row["recipient_id"]),
                str(row["event_type"]),
                str(row["version_id"]),
                row["created_at"],
            )
            for row in notifications
        ] == sorted(
            [
                (
                    fixture.owner_id,
                    "SKILL_PUBLISHED",
                    str(fixture.version_id),
                    first_time,
                ),
                (
                    fixture.subscriber_id,
                    "SUBSCRIPTION_NEW_VERSION",
                    str(fixture.version_id),
                    first_time,
                ),
            ]
        )
        assert sorted(
            (user_id, str(payload["eventType"]))
            for user_id, payload in fanout.published
        ) == sorted(
            [
                (fixture.owner_id, "SKILL_PUBLISHED"),
                (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
            ]
        )
    finally:
        release_first.set()
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_confirm_publish_postgres_succeeds_when_fanout_fails_and_replay_keeps_durable_rows_once() -> (
    None
):
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(engine)
    fanout = FailingFanout()
    first_time = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    replay_time = datetime(2026, 8, 23, 13, 0, tzinfo=UTC)
    try:
        first = await confirm_publish_skill_version(
            engine,
            _confirm_input(fixture, now=first_time),
            notification_fanout=fanout,
        )
        replay = await confirm_publish_skill_version(
            engine,
            _confirm_input(
                fixture,
                actor_id=fixture.admin_id,
                now=replay_time,
            ),
            notification_fanout=fanout,
        )

        async with engine.connect() as connection:
            notifications = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT recipient_id, event_type, created_at
                            FROM notification
                            WHERE entity_type = 'SKILL'
                              AND entity_id = :skill_id
                              AND category = 'PUBLISH'
                            ORDER BY recipient_id
                            """
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                )
                .mappings()
                .all()
            )

        assert first == replay
        assert [
            (str(row["recipient_id"]), str(row["event_type"]), row["created_at"])
            for row in notifications
        ] == sorted(
            [
                (fixture.owner_id, "SKILL_PUBLISHED", first_time),
                (
                    fixture.subscriber_id,
                    "SUBSCRIPTION_NEW_VERSION",
                    first_time,
                ),
            ]
        )
        assert fanout.attempts == 1
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_confirm_publish_postgres_owner_replay_preserves_original_admin_publisher_semantics() -> (
    None
):
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(engine)
    fanout = RecordingFanout()
    try:
        await confirm_publish_skill_version(
            engine,
            _confirm_input(fixture, actor_id=fixture.admin_id),
            notification_fanout=fanout,
        )
        await confirm_publish_skill_version(
            engine,
            _confirm_input(fixture, actor_id=fixture.owner_id),
            notification_fanout=fanout,
        )

        async with engine.connect() as connection:
            notifications = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT recipient_id, event_type
                            FROM notification
                            WHERE entity_type = 'SKILL'
                              AND entity_id = :skill_id
                              AND category = 'PUBLISH'
                            ORDER BY recipient_id
                            """
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                )
                .mappings()
                .all()
            )
            audit_actors = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT actor_user_id
                            FROM audit_log
                            WHERE action = 'CONFIRM_PUBLISH'
                              AND target_type = 'SKILL_VERSION'
                              AND target_id = :version_id
                            ORDER BY created_at ASC, id ASC
                            """
                        ),
                        {"version_id": fixture.version_id},
                    )
                )
                .scalars()
                .all()
            )
            search_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM skill_search_document WHERE skill_id = :skill_id"
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )

        assert list(audit_actors) == [fixture.admin_id]
        assert search_count == 1
        expected_notifications = sorted(
            [
                (fixture.owner_id, "SUBSCRIPTION_NEW_VERSION"),
                (fixture.subscriber_id, "SUBSCRIPTION_NEW_VERSION"),
            ]
        )
        assert [
            (str(row["recipient_id"]), str(row["event_type"])) for row in notifications
        ] == expected_notifications
        assert (
            sorted(
                (user_id, str(payload["eventType"]))
                for user_id, payload in fanout.published
            )
            == expected_notifications
        )
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_confirm_publish_postgres_rollback_leaves_no_publication_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    fixture = await _create_fixture(engine)
    fanout = RecordingFanout()

    async def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(lifecycle_skill, "_write_audit", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            await confirm_publish_skill_version(
                engine, _confirm_input(fixture), notification_fanout=fanout
            )

        async with engine.connect() as connection:
            status = str(
                (
                    await connection.execute(
                        text("SELECT status FROM skill_version WHERE id = :version_id"),
                        {"version_id": fixture.version_id},
                    )
                ).scalar_one()
            )
            search_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM skill_search_document WHERE skill_id = :skill_id"
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )
            notification_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM notification WHERE entity_type = 'SKILL' AND entity_id = :skill_id"
                        ),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )
        assert status == "UPLOADED"
        assert search_count == 0
        assert notification_count == 0
        assert fanout.published == []
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()
