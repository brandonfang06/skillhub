from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.skills.namespace_manifest import read_namespace_skill_manifest

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="SKILLHUB_TEST_DATABASE_URL is required for PostgreSQL integration",
)
@pytest.mark.anyio
async def test_namespace_manifest_filters_before_stable_pagination() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    suffix = uuid4().hex[:12]
    owner_id = f"manifest-owner-{suffix}"
    member_id = f"manifest-member-{suffix}"
    outsider_id = f"manifest-outsider-{suffix}"
    namespace = f"manifest-{suffix}"
    now = datetime.now(UTC)
    skill_ids: list[int] = []
    version_ids: list[int] = []
    namespace_id: int | None = None

    async def add_skill(
        connection: object,
        *,
        slug: str,
        visibility: str,
        status: str = "PUBLISHED",
        download_ready: bool = True,
        hidden: bool = False,
        yanked: bool = False,
        files: list[tuple[str, str]] | None = None,
    ) -> tuple[int, int]:
        skill_id = int(
            (
                await connection.execute(  # type: ignore[attr-defined]
                    text(
                        """
                        INSERT INTO skill (
                            namespace_id, slug, owner_id, visibility, status, hidden,
                            created_by, updated_by, updated_at
                        )
                        VALUES (
                            :namespace_id, :slug, :owner_id, :visibility, 'ACTIVE', :hidden,
                            :owner_id, :owner_id, :updated_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "namespace_id": namespace_id,
                        "slug": slug,
                        "owner_id": owner_id,
                        "visibility": visibility,
                        "hidden": hidden,
                        "updated_at": now,
                    },
                )
            ).scalar_one()
        )
        version_id = int(
            (
                await connection.execute(  # type: ignore[attr-defined]
                    text(
                        """
                        INSERT INTO skill_version (
                            skill_id, version, status, file_count, published_at,
                            download_ready, yanked_at, created_by
                        )
                        VALUES (
                            :skill_id, '1.0.0', :status, :file_count, :published_at,
                            :download_ready, :yanked_at, :owner_id
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "skill_id": skill_id,
                        "status": status,
                        "file_count": len(files or []),
                        "published_at": now if status == "PUBLISHED" else None,
                        "download_ready": download_ready,
                        "yanked_at": now if yanked else None,
                        "owner_id": owner_id,
                    },
                )
            ).scalar_one()
        )
        await connection.execute(  # type: ignore[attr-defined]
            text("UPDATE skill SET latest_version_id = :version_id WHERE id = :skill_id"),
            {"version_id": version_id, "skill_id": skill_id},
        )
        for file_path, digest in files or []:
            await connection.execute(  # type: ignore[attr-defined]
                text(
                    """
                    INSERT INTO skill_file (
                        version_id, file_path, file_size, sha256, storage_key
                    )
                    VALUES (:version_id, :file_path, 1, :sha256, :storage_key)
                    """
                ),
                {
                    "version_id": version_id,
                    "file_path": file_path,
                    "sha256": digest,
                    "storage_key": f"manifest/{suffix}/{slug}/{file_path}",
                },
            )
        skill_ids.append(skill_id)
        version_ids.append(version_id)
        return skill_id, version_id

    try:
        async with engine.begin() as connection:
            for user_id in (owner_id, member_id, outsider_id):
                await connection.execute(
                    text(
                        "INSERT INTO user_account (id, display_name) "
                        "VALUES (:user_id, :display_name)"
                    ),
                    {"user_id": user_id, "display_name": user_id},
                )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (
                                slug, display_name, type, status, created_by
                            )
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
                    VALUES
                      (:namespace_id, :owner_id, 'OWNER'),
                      (:namespace_id, :member_id, 'MEMBER')
                    """
                ),
                {
                    "namespace_id": namespace_id,
                    "owner_id": owner_id,
                    "member_id": member_id,
                },
            )

            alpha_skill_id, _ = await add_skill(
                connection,
                slug="alpha-public",
                visibility="PUBLIC",
                files=[("SKILL.md", "a" * 64), ("README.md", "b" * 64)],
            )
            pending_preview_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (
                                skill_id, version, status, file_count,
                                download_ready, created_by
                            )
                            VALUES (
                                :skill_id, '2.0.0', 'PENDING_REVIEW', 1,
                                FALSE, :owner_id
                            )
                            RETURNING id
                            """
                        ),
                        {"skill_id": alpha_skill_id, "owner_id": owner_id},
                    )
                ).scalar_one()
            )
            version_ids.append(pending_preview_id)
            await connection.execute(
                text(
                    "UPDATE skill SET latest_version_id = :version_id "
                    "WHERE id = :skill_id"
                ),
                {
                    "version_id": pending_preview_id,
                    "skill_id": alpha_skill_id,
                },
            )
            await add_skill(
                connection,
                slug="beta-team",
                visibility="NAMESPACE_ONLY",
                files=[("SKILL.md", "c" * 64)],
            )
            await add_skill(
                connection,
                slug="gamma-private",
                visibility="PRIVATE",
                files=[("SKILL.md", "d" * 64)],
            )
            await add_skill(
                connection,
                slug="hidden-public",
                visibility="PUBLIC",
                hidden=True,
                files=[("SKILL.md", "e" * 64)],
            )
            await add_skill(
                connection,
                slug="not-ready",
                visibility="PUBLIC",
                download_ready=False,
                files=[("SKILL.md", "f" * 64)],
            )
            await add_skill(
                connection,
                slug="pending",
                visibility="PUBLIC",
                status="PENDING_REVIEW",
                files=[("SKILL.md", "1" * 64)],
            )
            await add_skill(
                connection,
                slug="yanked",
                visibility="PUBLIC",
                yanked=True,
                files=[("SKILL.md", "2" * 64)],
            )

        first_page = await read_namespace_skill_manifest(
            engine,
            namespace=namespace,
            page=0,
            size=1,
            current_user_id=member_id,
        )
        second_page = await read_namespace_skill_manifest(
            engine,
            namespace=namespace,
            page=1,
            size=1,
            current_user_id=member_id,
        )
        owner_page = await read_namespace_skill_manifest(
            engine,
            namespace=namespace,
            page=0,
            size=100,
            current_user_id=owner_id,
        )
        outsider_page = await read_namespace_skill_manifest(
            engine,
            namespace=namespace,
            page=0,
            size=100,
            current_user_id=outsider_id,
        )

        assert first_page["nextCursor"] == "1"
        assert [item["slug"] for item in first_page["items"]] == ["alpha-public"]  # type: ignore[index]
        assert first_page["items"][0]["fingerprint"] == (  # type: ignore[index]
            "sha256:23dcc8064860209afe558bf02a647d7015d414e8adbc25fbc06f2ba568e09e02"
        )
        assert second_page["nextCursor"] is None
        assert [item["slug"] for item in second_page["items"]] == ["beta-team"]  # type: ignore[index]
        assert [item["slug"] for item in owner_page["items"]] == [  # type: ignore[index]
            "alpha-public",
            "beta-team",
            "gamma-private",
        ]
        assert [item["slug"] for item in outsider_page["items"]] == ["alpha-public"]  # type: ignore[index]
    finally:
        async with engine.begin() as connection:
            if version_ids:
                await connection.execute(
                    text(
                        "DELETE FROM skill_file "
                        "WHERE version_id = ANY(CAST(:version_ids AS bigint[]))"
                    ),
                    {"version_ids": version_ids},
                )
            if skill_ids:
                await connection.execute(
                    text(
                        "UPDATE skill SET latest_version_id = NULL "
                        "WHERE id = ANY(CAST(:skill_ids AS bigint[]))"
                    ),
                    {"skill_ids": skill_ids},
                )
            if version_ids:
                await connection.execute(
                    text(
                        "DELETE FROM skill_version "
                        "WHERE id = ANY(CAST(:version_ids AS bigint[]))"
                    ),
                    {"version_ids": version_ids},
                )
            if skill_ids:
                await connection.execute(
                    text(
                        "DELETE FROM skill WHERE id = ANY(CAST(:skill_ids AS bigint[]))"
                    ),
                    {"skill_ids": skill_ids},
                )
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
            await connection.execute(
                text(
                    "DELETE FROM user_account "
                    "WHERE id = ANY(CAST(:user_ids AS varchar[]))"
                ),
                {"user_ids": [owner_id, member_id, outsider_id]},
            )
        await engine.dispose()
