from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.review.query import read_review_detail


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_review_detail_returns_version_requested_visibility() -> None:
    suffix = uuid4().hex[:12]
    owner_id = f"review-visibility-{suffix}"
    submitter_id = f"review-submitter-{suffix}"
    namespace_slug = f"review-visibility-{suffix}"
    skill_slug = f"review-visibility-{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))

    namespace_id: int | None = None
    skill_id: int | None = None
    version_id: int | None = None
    review_task_id: int | None = None
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES (:owner_id, :owner_name), (:submitter_id, :submitter_name)
                    """
                ),
                {
                    "owner_id": owner_id,
                    "owner_name": "Requested visibility owner",
                    "submitter_id": submitter_id,
                    "submitter_name": "Requested visibility submitter",
                },
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
                        {"slug": namespace_slug, "display_name": namespace_slug, "owner_id": owner_id},
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES
                        (:namespace_id, :owner_id, 'OWNER'),
                        (:namespace_id, :submitter_id, 'MEMBER')
                    """
                ),
                {
                    "namespace_id": namespace_id,
                    "owner_id": owner_id,
                    "submitter_id": submitter_id,
                },
            )
            skill_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill (
                                namespace_id, slug, owner_id, visibility, created_by, updated_by
                            )
                            VALUES (
                                :namespace_id, :slug, :submitter_id, 'PUBLIC', :submitter_id, :submitter_id
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "namespace_id": namespace_id,
                            "slug": skill_slug,
                            "submitter_id": submitter_id,
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
                                skill_id, version, status, requested_visibility, created_by
                            )
                            VALUES (
                                :skill_id, '1.0.0', 'PENDING_REVIEW', 'NAMESPACE_ONLY', :submitter_id
                            )
                            RETURNING id
                            """
                        ),
                        {"skill_id": skill_id, "submitter_id": submitter_id},
                    )
                ).scalar_one()
            )
            review_task_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO review_task (
                                skill_version_id, namespace_id, status, submitted_by
                            )
                            VALUES (:version_id, :namespace_id, 'PENDING', :submitter_id)
                            RETURNING id
                            """
                        ),
                        {
                            "version_id": version_id,
                            "namespace_id": namespace_id,
                            "submitter_id": submitter_id,
                        },
                    )
                ).scalar_one()
            )

        detail = await read_review_detail(
            engine,
            review_task_id=review_task_id,
            user_id=owner_id,
        )

        assert detail["requestedVisibility"] == "NAMESPACE_ONLY"
        assert detail["approvalVisibility"] == "NAMESPACE_ONLY"
        assert detail["submittedBy"] == submitter_id
    finally:
        async with engine.begin() as connection:
            if review_task_id is not None:
                await connection.execute(
                    text("DELETE FROM review_task WHERE id = :id"),
                    {"id": review_task_id},
                )
            if version_id is not None:
                await connection.execute(
                    text("DELETE FROM skill_version WHERE id = :id"),
                    {"id": version_id},
                )
            if skill_id is not None:
                await connection.execute(
                    text("DELETE FROM skill WHERE id = :id"),
                    {"id": skill_id},
                )
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = :id"),
                    {"id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :id"),
                    {"id": namespace_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id IN (:owner_id, :submitter_id)"),
                {"owner_id": owner_id, "submitter_id": submitter_id},
            )
        await engine.dispose()
