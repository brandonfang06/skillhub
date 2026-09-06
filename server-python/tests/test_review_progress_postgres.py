from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.review.query import ReviewQueryError, list_my_review_progress, list_review_attempts


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_review_progress_groups_live_and_legacy_archived_attempts() -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL))
    suffix = uuid4().hex[:12]
    owner_id = f"progress-owner-{suffix}"
    author_id = f"progress-author-{suffix}"
    outsider_id = f"progress-outsider-{suffix}"
    namespace_slug = f"progress-team-{suffix}"
    skill_slug = f"agent-progress-{suffix}"
    now = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    namespace_id: int | None = None
    skill_id: int | None = None
    version_id: int | None = None
    task_ids: list[int] = []
    archived_task_id = 8_000_000_000 + int(suffix[:6], 16)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES (:owner, 'Progress owner'),
                           (:author, 'Progress author'),
                           (:outsider, 'Progress outsider')
                    """
                ),
                {"owner": owner_id, "author": author_id, "outsider": outsider_id},
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (slug, display_name, type, created_by)
                            VALUES (:slug, :slug, 'TEAM', :owner)
                            RETURNING id
                            """
                        ),
                        {"slug": namespace_slug, "owner": owner_id},
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES (:namespace_id, :owner, 'OWNER')
                    """
                ),
                {"namespace_id": namespace_id, "owner": owner_id},
            )
            skill_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill (
                                namespace_id, slug, owner_id, visibility,
                                created_by, updated_by
                            )
                            VALUES (
                                :namespace_id, :slug, :author, 'PUBLIC',
                                :author, :author
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "namespace_id": namespace_id,
                            "slug": skill_slug,
                            "author": author_id,
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
                            VALUES (:skill_id, '1.0.0', 'PENDING_REVIEW', :author)
                            RETURNING id
                            """
                        ),
                        {"skill_id": skill_id, "author": author_id},
                    )
                ).scalar_one()
            )
            for status, submitted_at, reviewed_at, reviewer, comment in (
                ("REJECTED", now - timedelta(hours=1), now, owner_id, "Fix metadata"),
                ("PENDING", now + timedelta(hours=1), None, None, None),
            ):
                task_ids.append(
                    int(
                        (
                            await connection.execute(
                                text(
                                    """
                                    INSERT INTO review_task (
                                        skill_version_id, skill_id, skill_version,
                                        namespace_id, status, submitted_by,
                                        reviewed_by, review_comment, submitted_at,
                                        reviewed_at
                                    )
                                    VALUES (
                                        :version_id, :skill_id, '1.0.0',
                                        :namespace_id, :status, :author,
                                        :reviewer,
                                        :comment, :submitted_at, :reviewed_at
                                    )
                                    RETURNING id
                                    """
                                ),
                                {
                                    "version_id": version_id,
                                    "skill_id": skill_id,
                                    "namespace_id": namespace_id,
                                    "status": status,
                                    "author": author_id,
                                    "reviewer": reviewer,
                                    "comment": comment,
                                    "submitted_at": submitted_at,
                                    "reviewed_at": reviewed_at,
                                },
                            )
                        ).scalar_one()
                    )
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO review_attempt_archive (
                        original_review_task_id, original_skill_version_id,
                        skill_id, namespace_id, namespace_slug, skill_slug,
                        version, status, submitted_by, reviewed_by,
                        review_comment, submitted_at, reviewed_at, files_json
                    )
                    VALUES (
                        :task_id, :version_id, :skill_id, :namespace_id,
                        :namespace_slug, :skill_slug, '1.0.0', 'REJECTED',
                        :author, :owner, 'Older rejection', :submitted_at,
                        :reviewed_at, '[]'::jsonb
                    )
                    """
                ),
                {
                    "task_id": archived_task_id,
                    "version_id": version_id,
                    "skill_id": skill_id,
                    "namespace_id": namespace_id,
                    "namespace_slug": namespace_slug,
                    "skill_slug": skill_slug,
                    "author": author_id,
                    "owner": owner_id,
                    "submitted_at": now - timedelta(days=1),
                    "reviewed_at": now - timedelta(days=1, hours=-1),
                },
            )

        progress = await list_my_review_progress(
            engine,
            status=None,
            query="AGENT-PROGRESS",
            page=0,
            size=20,
            user_id=author_id,
        )
        assert progress["total"] == 1
        assert progress["statusCounts"] == {
            "pending": 1,
            "approved": 0,
            "rejected": 0,
        }
        assert progress["items"][0]["latestReviewTaskId"] == task_ids[1]
        assert progress["items"][0]["attemptCount"] == 3

        author_attempts = await list_review_attempts(
            engine,
            review_task_id=task_ids[1],
            user_id=author_id,
            author_only=True,
        )
        reviewer_attempts = await list_review_attempts(
            engine,
            review_task_id=task_ids[1],
            user_id=owner_id,
        )
        assert [item["id"] for item in author_attempts] == [
            task_ids[1],
            task_ids[0],
            archived_task_id,
        ]
        assert [item["id"] for item in reviewer_attempts] == [
            task_ids[1],
            task_ids[0],
            archived_task_id,
        ]

        with pytest.raises(ReviewQueryError, match="review.no_permission"):
            await list_review_attempts(
                engine,
                review_task_id=task_ids[1],
                user_id=outsider_id,
                author_only=True,
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM review_attempt_archive WHERE original_review_task_id = :id"),
                {"id": archived_task_id},
            )
            if task_ids:
                await connection.execute(
                    text("DELETE FROM review_task WHERE id = ANY(CAST(:ids AS bigint[]))"),
                    {"ids": task_ids},
                )
            if version_id is not None:
                await connection.execute(text("DELETE FROM skill_version WHERE id = :id"), {"id": version_id})
            if skill_id is not None:
                await connection.execute(text("DELETE FROM skill WHERE id = :id"), {"id": skill_id})
            if namespace_id is not None:
                await connection.execute(text("DELETE FROM namespace_member WHERE namespace_id = :id"), {"id": namespace_id})
                await connection.execute(text("DELETE FROM namespace WHERE id = :id"), {"id": namespace_id})
            await connection.execute(
                text("DELETE FROM user_account WHERE id = ANY(CAST(:ids AS varchar[]))"),
                {"ids": [owner_id, author_id, outsider_id]},
            )
        await engine.dispose()
