from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata
from app.skills.label_projection import read_skill_label_projection
from app.skills.read_repository import read_skill_search

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_search_owner_and_label_projection_use_current_postgres_rows(
    tmp_path,
) -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=2, max_overflow=0)
    suffix = uuid4().hex[:12]
    owner_id = f"label-owner-{suffix}"
    namespace_slug = f"label-{suffix}"
    skill_slug = f"label-skill-{suffix}"
    label_slugs = [f"a-{suffix}", f"b-{suffix}"]
    namespace_id: int | None = None
    skill_id: int | None = None
    version_id: int | None = None
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"
                ),
                {"user_id": owner_id, "display_name": "Projection Owner"},
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
                        {"slug": namespace_slug, "owner_id": owner_id},
                    )
                ).scalar_one()
            )

        published = await execute_publish_write(
            engine,
            PublishWriteInput(
                namespace_id=namespace_id,
                namespace_slug=namespace_slug,
                slug=skill_slug,
                display_name="Projection Skill",
                summary="Owner and label projection",
                publisher_id=owner_id,
                visibility="PUBLIC",
                version="1.0.0",
                auto_publish=True,
                metadata=SkillMetadata(
                    name="Projection Skill",
                    description="Owner and label projection",
                    version="1.0.0",
                    frontmatter={
                        "name": "Projection Skill",
                        "description": "Owner and label projection",
                        "version": "1.0.0",
                    },
                ),
                entries=[
                    PackageEntry("SKILL.md", b"# Projection Skill\n", "text/markdown")
                ],
                storage_base_path=str(tmp_path),
                scanner_enabled=False,
                now=datetime.now(UTC),
            ),
        )
        skill_id = published.skill_id
        version_id = published.version_id

        async with engine.begin() as connection:
            label_ids: list[int] = []
            for index, label_slug in enumerate(label_slugs):
                label_id = int(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO label_definition (
                                    slug, type, visible_in_filter, sort_order, created_by
                                )
                                VALUES (:slug, 'RECOMMENDED', TRUE, :sort_order, :owner_id)
                                RETURNING id
                                """
                            ),
                            {
                                "slug": label_slug,
                                "sort_order": index,
                                "owner_id": owner_id,
                            },
                        )
                    ).scalar_one()
                )
                label_ids.append(label_id)
                await connection.execute(
                    text(
                        """
                        INSERT INTO label_translation (label_id, locale, display_name)
                        VALUES (:label_id, 'en', :english),
                               (:label_id, 'zh-TW', :traditional_chinese)
                        """
                    ),
                    {
                        "label_id": label_id,
                        "english": f"English {index}",
                        "traditional_chinese": f"繁中 {index}",
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_label (skill_id, label_id, created_by)
                        VALUES (:skill_id, :label_id, :owner_id)
                        """
                    ),
                    {
                        "skill_id": skill_id,
                        "label_id": label_id,
                        "owner_id": owner_id,
                    },
                )

        search = await read_skill_search(
            engine,
            keyword=None,
            namespace=namespace_slug,
            labels=[],
            sort="newest",
            page=0,
            size=20,
        )
        item = next(
            candidate
            for candidate in search["items"]  # type: ignore[union-attr]
            if candidate["id"] == skill_id
        )
        assert item["ownerId"] == owner_id
        assert item["ownerDisplayName"] == "Projection Owner"
        assert "labels" not in item

        labels = await read_skill_label_projection(
            engine,
            skill_ids=[skill_id, skill_id],
            locale="zh-TW",
        )
        assert labels[skill_id] == [
            {
                "slug": label_slugs[0],
                "type": "RECOMMENDED",
                "displayName": "繁中 0",
            },
            {
                "slug": label_slugs[1],
                "type": "RECOMMENDED",
                "displayName": "繁中 1",
            },
        ]
    finally:
        async with engine.begin() as connection:
            if skill_id is not None:
                await connection.execute(
                    text("DELETE FROM notification WHERE entity_type = 'SKILL' AND entity_id = :skill_id"),
                    {"skill_id": skill_id},
                )
                await connection.execute(
                    text("DELETE FROM skill_search_document WHERE skill_id = :skill_id"),
                    {"skill_id": skill_id},
                )
                await connection.execute(
                    text("DELETE FROM skill_label WHERE skill_id = :skill_id"),
                    {"skill_id": skill_id},
                )
                await connection.execute(
                    text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
                    {"skill_id": skill_id},
                )
            if version_id is not None:
                await connection.execute(
                    text("DELETE FROM skill_file WHERE version_id = :version_id"),
                    {"version_id": version_id},
                )
                await connection.execute(
                    text("DELETE FROM skill_version WHERE id = :version_id"),
                    {"version_id": version_id},
                )
            if skill_id is not None:
                await connection.execute(
                    text("DELETE FROM skill WHERE id = :skill_id"),
                    {"skill_id": skill_id},
                )
            await connection.execute(
                text("DELETE FROM label_definition WHERE slug = ANY(CAST(:slugs AS varchar[]))"),
                {"slugs": label_slugs},
            )
            await connection.execute(
                text("DELETE FROM audit_log WHERE actor_user_id = :owner_id"),
                {"owner_id": owner_id},
            )
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :owner_id"),
                {"owner_id": owner_id},
            )
        await engine.dispose()
