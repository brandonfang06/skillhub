from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.social.review import (
    SkillReviewError,
    SkillReviewInput,
    SkillReviewModerationInput,
    clear_skill_review,
    get_my_skill_review,
    list_skill_reviews,
    moderate_skill_review,
    upsert_skill_review,
)


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_text_review_moderation_retains_score_and_hidden_state_on_author_edit() -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL))
    suffix = uuid4().hex[:10]
    owner = f"review-owner-{suffix}"
    author = f"review-author-{suffix}"
    moderator = f"review-moderator-{suffix}"
    namespace_id: int | None = None
    skill_id: int | None = None
    now = datetime(2026, 9, 6, tzinfo=UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO user_account (id, display_name) VALUES (:owner, 'Owner'), (:author, 'Author'), (:moderator, 'Moderator')"), {"owner": owner, "author": author, "moderator": moderator})
            namespace_id = int((await connection.execute(text("INSERT INTO namespace (slug, display_name, type, status, created_by) VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :owner) RETURNING id"), {"slug": f"reviews-{suffix}", "owner": owner})).scalar_one())
            skill_id = int((await connection.execute(text("INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by) VALUES (:namespace_id, 'demo', 'Demo', 'summary', :owner, 'PUBLIC', 'ACTIVE', :owner, :owner) RETURNING id"), {"namespace_id": namespace_id, "owner": owner})).scalar_one())
            published_id = int((await connection.execute(text("INSERT INTO skill_version (skill_id, version, status, created_by, published_at, bundle_ready, download_ready) VALUES (:skill_id, '1.0.0', 'PUBLISHED', :owner, :now, TRUE, TRUE) RETURNING id"), {"skill_id": skill_id, "owner": owner, "now": now})).scalar_one())
            pending_id = int((await connection.execute(text("INSERT INTO skill_version (skill_id, version, status, created_by) VALUES (:skill_id, '1.1.0', 'PENDING_REVIEW', :owner) RETURNING id"), {"skill_id": skill_id, "owner": owner})).scalar_one())
            await connection.execute(text("UPDATE skill SET latest_version_id = :pending_id WHERE id = :skill_id"), {"pending_id": pending_id, "skill_id": skill_id})

        created = await upsert_skill_review(engine, SkillReviewInput(skill_id=skill_id, user_id=author, score=5, review_text="Excellent", expected_lock_version=0, now=now))
        assert created["lockVersion"] == 0
        assert (await list_skill_reviews(engine, skill_id=skill_id, user_id=None, platform_roles=set(), page=0, size=20))["total"] == 1

        hidden = await moderate_skill_review(engine, SkillReviewModerationInput(review_id=int(created["reviewId"]), moderator_id=moderator, action="HIDE", reason="Contains secrets", now=now))
        assert hidden["status"] == "HIDDEN"
        assert (await list_skill_reviews(engine, skill_id=skill_id, user_id=None, platform_roles=set(), page=0, size=20))["total"] == 0

        mine = await get_my_skill_review(engine, skill_id=skill_id, user_id=author)
        assert mine["status"] == "HIDDEN"
        with pytest.raises(SkillReviewError, match="error.review.concurrent_update") as stale:
            await upsert_skill_review(engine, SkillReviewInput(skill_id=skill_id, user_id=author, score=4, review_text="Stale edit", expected_lock_version=0, now=now))
        assert stale.value.status_code == 409
        edited = await upsert_skill_review(engine, SkillReviewInput(skill_id=skill_id, user_id=author, score=4, review_text="Still useful", expected_lock_version=1, now=now))
        assert edited["status"] == "HIDDEN"

        restored = await moderate_skill_review(engine, SkillReviewModerationInput(review_id=int(created["reviewId"]), moderator_id=moderator, action="RESTORE", now=now))
        assert restored["status"] == "VISIBLE"

        cleared = await clear_skill_review(engine, skill_id=skill_id, user_id=author, expected_lock_version=3, now=now)
        assert cleared["reviewed"] is False
        async with engine.connect() as connection:
            row = (await connection.execute(text("SELECT score, review_text FROM skill_rating WHERE skill_id = :skill_id AND user_id = :author"), {"skill_id": skill_id, "author": author})).mappings().one()
            stats = (await connection.execute(text("SELECT rating_count FROM skill WHERE id = :skill_id"), {"skill_id": skill_id})).scalar_one()
        assert row["score"] == 4
        assert row["review_text"] is None
        assert stats == 1
        assert published_id > 0
    finally:
        if skill_id is not None:
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM audit_log WHERE actor_user_id IN (:owner, :author, :moderator)"), {"owner": owner, "author": author, "moderator": moderator})
                await connection.execute(text("DELETE FROM skill_rating WHERE skill_id = :skill_id"), {"skill_id": skill_id})
                await connection.execute(text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"), {"skill_id": skill_id})
                await connection.execute(text("DELETE FROM skill_version WHERE skill_id = :skill_id"), {"skill_id": skill_id})
                await connection.execute(text("DELETE FROM skill WHERE id = :skill_id"), {"skill_id": skill_id})
        if namespace_id is not None:
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM namespace WHERE id = :namespace_id"), {"namespace_id": namespace_id})
                await connection.execute(text("DELETE FROM user_account WHERE id IN (:owner, :author, :moderator)"), {"owner": owner, "author": author, "moderator": moderator})
        await engine.dispose()
