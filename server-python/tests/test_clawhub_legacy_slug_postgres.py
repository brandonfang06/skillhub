from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.skills.read_repository import read_clawhub_legacy_slug_coordinate

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


async def _insert_published_skill(
    engine: AsyncEngine,
    *,
    namespace_id: int,
    slug: str,
    owner_id: str,
    visibility: str,
) -> tuple[int, int]:
    async with engine.begin() as connection:
        skill_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill (
                            namespace_id, slug, display_name, owner_id, visibility,
                            status, created_by, updated_by
                        )
                        VALUES (
                            :namespace_id, :slug, :slug, :owner_id, :visibility,
                            'ACTIVE', :owner_id, :owner_id
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "namespace_id": namespace_id,
                        "slug": slug,
                        "owner_id": owner_id,
                        "visibility": visibility,
                    },
                )
            ).scalar_one()
        )
        version_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_version (skill_id, version, status, created_by)
                        VALUES (:skill_id, '1.0.0', 'PUBLISHED', :owner_id)
                        RETURNING id
                        """
                    ),
                    {"skill_id": skill_id, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text("UPDATE skill SET latest_version_id = :version_id WHERE id = :skill_id"),
            {"skill_id": skill_id, "version_id": version_id},
        )
    return skill_id, version_id


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_legacy_slug_preference_is_public_then_global_in_postgres() -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=2, max_overflow=0)
    suffix = uuid4().hex[:12]
    owner_id = f"legacy-owner-{suffix}"
    team_slug = f"legacy-team-{suffix}"
    global_wins_slug = f"legacy-global-wins-{suffix}"
    public_wins_slug = f"legacy-public-wins-{suffix}"
    team_namespace_id: int | None = None
    skill_ids: list[int] = []
    version_ids: list[int] = []
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) VALUES (:user_id, :display_name)"
                ),
                {"user_id": owner_id, "display_name": "Legacy Slug Owner"},
            )
            team_namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (slug, display_name, type, status, created_by)
                            VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :owner_id)
                            RETURNING id
                            """
                        ),
                        {"slug": team_slug, "owner_id": owner_id},
                    )
                ).scalar_one()
            )
            global_namespace_id = int(
                (
                    await connection.execute(
                        text(
                            "SELECT id FROM namespace WHERE slug = 'global' AND type = 'GLOBAL'"
                        )
                    )
                ).scalar_one()
            )

        for namespace_id, slug, visibility in (
            (team_namespace_id, global_wins_slug, "PRIVATE"),
            (global_namespace_id, global_wins_slug, "PUBLIC"),
            (global_namespace_id, public_wins_slug, "PRIVATE"),
            (team_namespace_id, public_wins_slug, "PUBLIC"),
        ):
            skill_id, version_id = await _insert_published_skill(
                engine,
                namespace_id=namespace_id,
                slug=slug,
                owner_id=owner_id,
                visibility=visibility,
            )
            skill_ids.append(skill_id)
            version_ids.append(version_id)

        assert await read_clawhub_legacy_slug_coordinate(
            engine,
            global_wins_slug,
        ) == ("global", global_wins_slug)
        assert await read_clawhub_legacy_slug_coordinate(
            engine,
            public_wins_slug,
        ) == (team_slug, public_wins_slug)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE skill SET latest_version_id = NULL WHERE id = ANY(CAST(:ids AS bigint[]))"),
                {"ids": skill_ids or [-1]},
            )
            await connection.execute(
                text("DELETE FROM skill_version WHERE id = ANY(CAST(:ids AS bigint[]))"),
                {"ids": version_ids or [-1]},
            )
            await connection.execute(
                text("DELETE FROM skill WHERE id = ANY(CAST(:ids AS bigint[]))"),
                {"ids": skill_ids or [-1]},
            )
            if team_namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": team_namespace_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :owner_id"),
                {"owner_id": owner_id},
            )
        await engine.dispose()
