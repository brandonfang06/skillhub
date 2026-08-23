from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_namespace.read_repository import (
    JAVA_INT_MAX,
    AdminNamespaceReadError,
    get_admin_namespace,
    list_admin_namespace_members,
    list_admin_namespaces,
    search_admin_namespace_member_candidates,
)
from app.namespace.read import NamespaceReadError, get_namespace
from app.namespace_analytics.repository import list_namespace_analytics

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_namespace_read_surface_uses_management_counts_and_platform_override() -> (
    None
):
    suffix = uuid4().hex
    admin_id = f"admin-{suffix}"
    owner_id = f"owner-{suffix}"
    member_id = f"member-{suffix}"
    candidate_id = f"candidate-{suffix}"
    existing_candidate_id = f"existing-{suffix}"
    inactive_id = f"inactive-{suffix}"
    active_slug = f"admin-active-{suffix}"
    frozen_slug = f"admin-frozen-{suffix}"
    archived_slug = f"admin-archived-{suffix}"
    now = datetime.now(UTC).replace(tzinfo=None)
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_ids: list[int] = []
    skill_ids: list[int] = []
    version_ids: list[int] = []

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name, email, status)
                    VALUES
                      (:admin_id, 'Platform Admin', :admin_email, 'ACTIVE'),
                      (:owner_id, 'Owner User', :owner_email, 'ACTIVE'),
                      (:member_id, 'Member User', :member_email, 'ACTIVE'),
                      (:candidate_id, 'Candidate User', :candidate_email, 'ACTIVE'),
                      (:existing_candidate_id, 'Candidate Existing', :existing_email, 'ACTIVE'),
                      (:inactive_id, 'Candidate Inactive', :inactive_email, 'DISABLED')
                    """
                ),
                {
                    "admin_id": admin_id,
                    "admin_email": f"{admin_id}@example.test",
                    "owner_id": owner_id,
                    "owner_email": f"{owner_id}@example.test",
                    "member_id": member_id,
                    "member_email": f"{member_id}@example.test",
                    "candidate_id": candidate_id,
                    "candidate_email": f"{candidate_id}@example.test",
                    "existing_candidate_id": existing_candidate_id,
                    "existing_email": f"{existing_candidate_id}@example.test",
                    "inactive_id": inactive_id,
                    "inactive_email": f"{inactive_id}@example.test",
                },
            )
            namespace_rows = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO namespace (
                            slug, display_name, type, description, status, created_by,
                            created_at, updated_at
                        )
                        VALUES
                          (:active_slug, 'Alpha Team', 'TEAM', 'mixed catalog', 'ACTIVE', :owner_id, :created_at, :active_at),
                          (:frozen_slug, 'Frozen Team', 'TEAM', 'historical', 'FROZEN', :owner_id, :created_at, :frozen_at),
                          (:archived_slug, 'Archived Team', 'TEAM', 'historical', 'ARCHIVED', :owner_id, :created_at, :archived_at)
                        RETURNING id, slug
                        """
                        ),
                        {
                            "active_slug": active_slug,
                            "frozen_slug": frozen_slug,
                            "archived_slug": archived_slug,
                            "owner_id": owner_id,
                            "created_at": now - timedelta(days=5),
                            "active_at": now,
                            "frozen_at": now - timedelta(days=1),
                            "archived_at": now - timedelta(days=2),
                        },
                    )
                )
                .mappings()
                .all()
            )
            by_slug = {str(row["slug"]): int(row["id"]) for row in namespace_rows}
            namespace_ids = list(by_slug.values())
            active_id = by_slug[active_slug]
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES
                      (:namespace_id, :owner_id, 'OWNER'),
                      (:namespace_id, :member_id, 'MEMBER'),
                      (:namespace_id, :existing_id, 'MEMBER')
                    """
                ),
                {
                    "namespace_id": active_id,
                    "owner_id": owner_id,
                    "member_id": member_id,
                    "existing_id": existing_candidate_id,
                },
            )
            skill_rows = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO skill (
                            namespace_id, slug, owner_id, status, created_by, updated_by
                        )
                        VALUES
                          (:namespace_id, :published_slug, :owner_id, 'ACTIVE', :owner_id, :owner_id),
                          (:namespace_id, :unpublished_slug, :owner_id, 'ACTIVE', :owner_id, :owner_id),
                          (:namespace_id, :archived_skill_slug, :owner_id, 'ARCHIVED', :owner_id, :owner_id)
                        RETURNING id, slug
                        """
                        ),
                        {
                            "namespace_id": active_id,
                            "published_slug": f"published-{suffix}",
                            "unpublished_slug": f"unpublished-{suffix}",
                            "archived_skill_slug": f"archived-{suffix}",
                            "owner_id": owner_id,
                        },
                    )
                )
                .mappings()
                .all()
            )
            skill_by_slug = {str(row["slug"]): int(row["id"]) for row in skill_rows}
            skill_ids = list(skill_by_slug.values())
            published_skill_id = skill_by_slug[f"published-{suffix}"]
            version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (
                                skill_id, version, status, created_by, published_at
                            )
                            VALUES (:skill_id, '1.0.0', 'PUBLISHED', :owner_id, :published_at)
                            RETURNING id
                            """
                        ),
                        {
                            "skill_id": published_skill_id,
                            "owner_id": owner_id,
                            "published_at": now,
                        },
                    )
                ).scalar_one()
            )
            version_ids = [version_id]
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_file (
                        version_id, file_path, file_size, sha256, storage_key
                    )
                    VALUES (:version_id, 'SKILL.md', 1, :sha256, :storage_key)
                    """
                ),
                {
                    "version_id": version_id,
                    "sha256": "a" * 64,
                    "storage_key": f"admin-namespace/{suffix}/SKILL.md",
                },
            )

        listing = await list_admin_namespaces(
            engine,
            keyword=suffix,
            status="active",
            namespace_type="team",
            page=-5,
            size=500,
            actor_user_id=admin_id,
        )
        assert listing["total"] == 1
        assert listing["page"] == 0
        assert listing["size"] == 100
        item = listing["items"][0]
        assert item["slug"] == active_slug
        assert item["stats"] == {"memberCount": 3, "skillCount": 3}
        assert item["permissions"]["currentUserRole"] is None
        assert item["permissions"]["platformOverride"] is True

        async with engine.connect() as connection:
            expected_stats = dict(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*) AS total,
                                   COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active,
                                   COUNT(*) FILTER (WHERE status = 'FROZEN') AS frozen,
                                   COUNT(*) FILTER (WHERE status = 'ARCHIVED') AS archived
                            FROM namespace
                            """
                        )
                    )
                )
                .mappings()
                .one()
            )
        assert listing["stats"] == {
            key: int(value) for key, value in expected_stats.items()
        }

        analytics = await list_namespace_analytics(
            engine,
            query=active_slug,
            namespace_type="TEAM",
            namespace_status="ACTIVE",
            start_time=None,
            end_time=None,
            source=None,
            sort="skills",
            direction="desc",
            page=0,
            size=20,
            retention_months=12,
        )
        assert analytics["items"][0]["skillCount"] == 1
        assert item["stats"]["skillCount"] == 3

        detail = await get_admin_namespace(
            engine,
            slug=archived_slug,
            actor_user_id=admin_id,
        )
        assert detail["status"] == "ARCHIVED"
        assert detail["permissions"]["canRestore"] is True
        global_detail = await get_admin_namespace(
            engine,
            slug="global",
            actor_user_id=admin_id,
        )
        assert global_detail["permissions"]["immutable"] is True

        with pytest.raises(
            AdminNamespaceReadError, match="error.namespace.system.immutable"
        ):
            await search_admin_namespace_member_candidates(
                engine,
                slug="global",
                search="x",
                size=10,
            )
        with pytest.raises(AdminNamespaceReadError, match="error.namespace.readonly"):
            await search_admin_namespace_member_candidates(
                engine,
                slug=frozen_slug,
                search=candidate_id,
                size=10,
            )
        with pytest.raises(AdminNamespaceReadError, match="error.namespace.readonly"):
            await search_admin_namespace_member_candidates(
                engine,
                slug=archived_slug,
                search=candidate_id,
                size=10,
            )

        members = await list_admin_namespace_members(
            engine,
            slug=active_slug,
            page=-1,
            size=999,
        )
        assert members["total"] == 3
        assert members["page"] == 0
        assert members["size"] == 100

        max_page_listing = await list_admin_namespaces(
            engine,
            keyword=active_slug,
            status="ACTIVE",
            namespace_type="TEAM",
            page=JAVA_INT_MAX,
            size=100,
            actor_user_id=admin_id,
        )
        assert max_page_listing["page"] == JAVA_INT_MAX
        assert max_page_listing["items"] == []
        max_page_members = await list_admin_namespace_members(
            engine,
            slug=active_slug,
            page=JAVA_INT_MAX,
            size=100,
        )
        assert max_page_members["page"] == JAVA_INT_MAX
        assert max_page_members["items"] == []

        with pytest.raises(
            AdminNamespaceReadError, match="error.pagination.page.invalid"
        ) as oversized_list:
            await list_admin_namespaces(
                engine,
                keyword=active_slug,
                status="ACTIVE",
                namespace_type="TEAM",
                page=JAVA_INT_MAX + 1,
                size=100,
                actor_user_id=admin_id,
            )
        assert oversized_list.value.status_code == 400
        with pytest.raises(
            AdminNamespaceReadError, match="error.pagination.page.invalid"
        ) as oversized_members:
            await list_admin_namespace_members(
                engine,
                slug=active_slug,
                page=JAVA_INT_MAX + 1,
                size=100,
            )
        assert oversized_members.value.status_code == 400

        candidates = await search_admin_namespace_member_candidates(
            engine,
            slug=active_slug,
            search=candidate_id,
            size=99,
        )
        assert [candidate["userId"] for candidate in candidates] == [candidate_id]

        with pytest.raises(
            NamespaceReadError, match="error.namespace.membership.required"
        ):
            await get_namespace(
                engine,
                slug=active_slug,
                user_id=admin_id,
            )
    finally:
        async with engine.begin() as connection:
            if version_ids:
                await connection.execute(
                    text("DELETE FROM skill_file WHERE version_id = ANY(:version_ids)"),
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
            if namespace_ids:
                await connection.execute(
                    text(
                        "DELETE FROM namespace_member WHERE namespace_id = ANY(:namespace_ids)"
                    ),
                    {"namespace_ids": namespace_ids},
                )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = ANY(:namespace_ids)"),
                    {"namespace_ids": namespace_ids},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = ANY(:user_ids)"),
                {
                    "user_ids": [
                        admin_id,
                        owner_id,
                        member_id,
                        candidate_id,
                        existing_candidate_id,
                        inactive_id,
                    ]
                },
            )
        await engine.dispose()
