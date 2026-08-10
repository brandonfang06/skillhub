from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.lifecycle import skill as lifecycle_skill
from app.lifecycle.skill import (
    SkillLifecycleError,
    SkillSubmitReviewInput,
    SkillVersionDeleteInput,
    delete_skill_version,
    submit_skill_version_for_review,
)
from app.review.query import read_review_detail

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@dataclass(frozen=True)
class DeleteFixture:
    user_id: str
    namespace_id: int
    namespace: str
    skill_id: int
    slug: str
    version_ids: tuple[int, ...]
    review_task_id: int | None


async def _create_fixture(
    engine: AsyncEngine,
    *,
    versions: tuple[tuple[str, str], ...],
    rejected_review_version: str | None = None,
) -> DeleteFixture:
    suffix = uuid4().hex[:12]
    user_id = f"delete-test-{suffix}"
    namespace = f"delete-test-{suffix}"
    slug = f"delete-test-{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"),
            {"user_id": user_id, "display_name": "Delete integration test"},
        )
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, created_by)
                        VALUES (:slug, :display_name, 'TEAM', :user_id)
                        RETURNING id
                        """
                    ),
                    {"slug": namespace, "display_name": namespace, "user_id": user_id},
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
                    {"namespace_id": namespace_id, "slug": slug, "user_id": user_id},
                )
            ).scalar_one()
        )
        version_ids: list[int] = []
        version_ids_by_name: dict[str, int] = {}
        for version, status in versions:
            version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (skill_id, version, status, created_by)
                            VALUES (:skill_id, :version, :status, :user_id)
                            RETURNING id
                            """
                        ),
                        {"skill_id": skill_id, "version": version, "status": status, "user_id": user_id},
                    )
                ).scalar_one()
            )
            version_ids.append(version_id)
            version_ids_by_name[version] = version_id

        review_task_id: int | None = None
        if rejected_review_version is not None:
            review_task_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO review_task (
                                skill_version_id, namespace_id, status, submitted_by, reviewed_by,
                                review_comment, reviewed_at
                            )
                            VALUES (
                                :version_id, :namespace_id, 'REJECTED', :user_id, :user_id,
                                'Fix validation', CURRENT_TIMESTAMP
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "version_id": version_ids_by_name[rejected_review_version],
                            "namespace_id": namespace_id,
                            "user_id": user_id,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO notification (
                        recipient_id, category, event_type, title, entity_type, entity_id
                    )
                    VALUES (:user_id, 'REVIEW', 'REVIEW_SUBMITTED', 'Review submitted', 'REVIEW', :review_task_id)
                    """
                ),
                {"user_id": user_id, "review_task_id": review_task_id},
            )

    return DeleteFixture(
        user_id=user_id,
        namespace_id=namespace_id,
        namespace=namespace,
        skill_id=skill_id,
        slug=slug,
        version_ids=tuple(version_ids),
        review_task_id=review_task_id,
    )


async def _cleanup_fixture(engine: AsyncEngine, fixture: DeleteFixture) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM notification WHERE recipient_id = :user_id"), {"user_id": fixture.user_id})
        await connection.execute(text("DELETE FROM audit_log WHERE actor_user_id = :user_id"), {"user_id": fixture.user_id})
        await connection.execute(
            text("DELETE FROM review_attempt_archive WHERE namespace_id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("DELETE FROM review_task WHERE namespace_id = :namespace_id"),
            {"namespace_id": fixture.namespace_id},
        )
        await connection.execute(
            text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
            {"skill_id": fixture.skill_id},
        )
        await connection.execute(text("DELETE FROM skill_version WHERE skill_id = :skill_id"), {"skill_id": fixture.skill_id})
        await connection.execute(text("DELETE FROM skill WHERE id = :skill_id"), {"skill_id": fixture.skill_id})
        await connection.execute(text("DELETE FROM namespace WHERE id = :namespace_id"), {"namespace_id": fixture.namespace_id})
        await connection.execute(text("DELETE FROM user_account WHERE id = :user_id"), {"user_id": fixture.user_id})


def _delete_input(fixture: DeleteFixture, version: str) -> SkillVersionDeleteInput:
    return SkillVersionDeleteInput(
        namespace=fixture.namespace,
        slug=fixture.slug,
        version=version,
        user_id=fixture.user_id,
        request_id=f"delete-{version}",
        client_ip="127.0.0.1",
        user_agent="pytest-postgres",
    )


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_delete_rejected_version_preserves_review_history_and_notification_link_on_postgres() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    fixture = await _create_fixture(
        engine,
        versions=(("1.0.0", "PUBLISHED"), ("1.1.0", "REJECTED")),
        rejected_review_version="1.1.0",
    )
    try:
        result = await delete_skill_version(engine, _delete_input(fixture, "1.1.0"))

        async with engine.connect() as connection:
            version_count = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM skill_version WHERE skill_id = :skill_id"),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )
            review_count = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM review_task WHERE namespace_id = :namespace_id"),
                        {"namespace_id": fixture.namespace_id},
                    )
                ).scalar_one()
            )
            archive_row = (
                await connection.execute(
                    text(
                        """
                        SELECT original_review_task_id, archive_reason,
                               replacement_version_id, replacement_review_task_id
                        FROM review_attempt_archive
                        WHERE namespace_id = :namespace_id
                        """
                    ),
                    {"namespace_id": fixture.namespace_id},
                )
            ).mappings().one_or_none()
            notification_count = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM notification WHERE recipient_id = :user_id"),
                        {"user_id": fixture.user_id},
                    )
                ).scalar_one()
            )
        assert fixture.review_task_id is not None
        detail = await read_review_detail(engine, review_task_id=fixture.review_task_id, user_id=fixture.user_id)

        assert result.response["versionId"] == fixture.version_ids[1]
        assert version_count == 1
        assert review_count == 0
        assert archive_row is not None
        assert int(archive_row["original_review_task_id"]) == fixture.review_task_id
        assert archive_row["archive_reason"] == "REJECTED_VERSION_DELETE"
        assert archive_row["replacement_version_id"] is None
        assert archive_row["replacement_review_task_id"] is None
        assert notification_count == 1
        assert detail["id"] == fixture.review_task_id
        assert detail["status"] == "REJECTED"
        assert detail["superseded"] is True
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_concurrent_version_deletes_preserve_last_version_on_postgres() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(
        engine,
        versions=(("1.0.0", "UPLOADED"), ("1.1.0", "REJECTED")),
    )
    try:
        outcomes = await asyncio.gather(
            delete_skill_version(engine, _delete_input(fixture, "1.0.0")),
            delete_skill_version(engine, _delete_input(fixture, "1.1.0")),
            return_exceptions=True,
        )

        successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        async with engine.connect() as connection:
            remaining_count = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM skill_version WHERE skill_id = :skill_id"),
                        {"skill_id": fixture.skill_id},
                    )
                ).scalar_one()
            )

        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], SkillLifecycleError)
        assert str(failures[0]) == "error.skill.version.delete.lastVersion"
        assert remaining_count == 1
    finally:
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_delete_racing_review_submit_returns_conflict_instead_of_foreign_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(
        engine,
        versions=(("1.0.0", "PUBLISHED"), ("1.1.0", "UPLOADED")),
    )
    version_locked = asyncio.Event()
    release_delete = asyncio.Event()
    original_reader = lifecycle_skill._read_versions_for_update

    async def paused_reader(connection: object, skill_id: int) -> list[dict[str, object]]:
        rows = await original_reader(connection, skill_id)
        version_locked.set()
        await release_delete.wait()
        return rows

    monkeypatch.setattr(lifecycle_skill, "_read_versions_for_update", paused_reader)
    try:
        delete_task = asyncio.create_task(delete_skill_version(engine, _delete_input(fixture, "1.1.0")))
        await asyncio.wait_for(version_locked.wait(), timeout=5)
        submit_task = asyncio.create_task(
            submit_skill_version_for_review(
                engine,
                SkillSubmitReviewInput(
                    namespace=fixture.namespace,
                    slug=fixture.slug,
                    version="1.1.0",
                    target_visibility="PUBLIC",
                    user_id=fixture.user_id,
                ),
            )
        )
        await asyncio.sleep(0.05)
        release_delete.set()
        delete_result, submit_result = await asyncio.gather(delete_task, submit_task, return_exceptions=True)

        assert not isinstance(delete_result, BaseException)
        assert isinstance(submit_result, SkillLifecycleError)
        assert submit_result.status_code == 409
        assert str(submit_result) == "review.concurrent_update"
    finally:
        release_delete.set()
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_review_submit_winning_delete_race_rejects_delete_without_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    fixture = await _create_fixture(
        engine,
        versions=(("1.0.0", "PUBLISHED"), ("1.1.0", "UPLOADED")),
    )
    submit_locked = asyncio.Event()
    release_submit = asyncio.Event()

    async def paused_notifications(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        submit_locked.set()
        await release_submit.wait()
        return []

    monkeypatch.setattr(lifecycle_skill, "write_review_submitted_notifications", paused_notifications)
    try:
        submit_task = asyncio.create_task(
            submit_skill_version_for_review(
                engine,
                SkillSubmitReviewInput(
                    namespace=fixture.namespace,
                    slug=fixture.slug,
                    version="1.1.0",
                    target_visibility="PUBLIC",
                    user_id=fixture.user_id,
                ),
            )
        )
        await asyncio.wait_for(submit_locked.wait(), timeout=5)
        delete_task = asyncio.create_task(delete_skill_version(engine, _delete_input(fixture, "1.1.0")))
        await asyncio.sleep(0.05)
        release_submit.set()
        submit_result, delete_result = await asyncio.gather(submit_task, delete_task, return_exceptions=True)

        assert not isinstance(submit_result, BaseException)
        assert submit_result["status"] == "PENDING_REVIEW"
        assert isinstance(delete_result, SkillLifecycleError)
        assert str(delete_result) == "error.skill.version.delete.unsupported"
    finally:
        release_submit.set()
        await _cleanup_fixture(engine, fixture)
        await engine.dispose()
