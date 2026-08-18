from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


async def _expect_integrity_error(connection: object, statement: str, params: dict[str, object]) -> None:
    with pytest.raises(IntegrityError):
        async with connection.begin_nested():  # type: ignore[attr-defined]
            await connection.execute(text(statement), params)  # type: ignore[attr-defined]


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_oss_source_schema_enforces_identity_and_cascades_version_provenance() -> None:
    suffix = uuid4().hex[:12]
    user_id = f"oss-schema-{suffix}"
    namespace_slug = f"oss-schema-{suffix}"
    repository_url = f"https://github.com/example/{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO user_account (id, display_name) VALUES (:id, :display_name)"),
                {"id": user_id, "display_name": "OSS schema test"},
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (slug, display_name, type, created_by)
                            VALUES (:slug, :display_name, 'TEAM', :created_by)
                            RETURNING id
                            """
                        ),
                        {"slug": namespace_slug, "display_name": namespace_slug, "created_by": user_id},
                    )
                ).scalar_one()
            )
            skill_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill (namespace_id, slug, owner_id, created_by, updated_by)
                            VALUES (:namespace_id, 'schema-skill', :owner_id, :owner_id, :owner_id)
                            RETURNING id
                            """
                        ),
                        {"namespace_id": namespace_id, "owner_id": user_id},
                    )
                ).scalar_one()
            )
            version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (skill_id, version, status, created_by)
                            VALUES (:skill_id, '1.0.0', 'PENDING_REVIEW', :created_by)
                            RETURNING id
                            """
                        ),
                        {"skill_id": skill_id, "created_by": user_id},
                    )
                ).scalar_one()
            )
            namespace_source_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO local_oss_namespace_source (namespace_id, repository_url, created_by)
                            VALUES (:namespace_id, :repository_url, :created_by)
                            RETURNING id
                            """
                        ),
                        {"namespace_id": namespace_id, "repository_url": repository_url, "created_by": user_id},
                    )
                ).scalar_one()
            )
            skill_source_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO local_oss_skill_source (namespace_source_id, source_path, skill_id, created_by)
                            VALUES (:namespace_source_id, 'skills/schema-skill', :skill_id, :created_by)
                            RETURNING id
                            """
                        ),
                        {
                            "namespace_source_id": namespace_source_id,
                            "skill_id": skill_id,
                            "created_by": user_id,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO local_oss_skill_version_source (
                        skill_source_id, skill_version_id, repository_revision_sha,
                        source_ref_type, source_ref, content_fingerprint, imported_by
                    )
                    VALUES (
                        :skill_source_id, :skill_version_id, :sha,
                        'BRANCH', 'main', :fingerprint, :imported_by
                    )
                    """
                ),
                {
                    "skill_source_id": skill_source_id,
                    "skill_version_id": version_id,
                    "sha": "a" * 40,
                    "fingerprint": "b" * 64,
                    "imported_by": user_id,
                },
            )

            await _expect_integrity_error(
                connection,
                """
                INSERT INTO local_oss_namespace_source (namespace_id, repository_url, created_by)
                VALUES (:namespace_id, :repository_url, :created_by)
                """,
                {"namespace_id": namespace_id, "repository_url": repository_url, "created_by": user_id},
            )
            await _expect_integrity_error(
                connection,
                """
                INSERT INTO local_oss_skill_source (namespace_source_id, source_path, skill_id, created_by)
                VALUES (:namespace_source_id, 'skills/schema-skill', :skill_id, :created_by)
                """,
                {"namespace_source_id": namespace_source_id, "skill_id": skill_id, "created_by": user_id},
            )
            await _expect_integrity_error(
                connection,
                """
                INSERT INTO local_oss_skill_version_source (
                    skill_source_id, skill_version_id, repository_revision_sha,
                    source_ref_type, content_fingerprint, imported_by
                )
                VALUES (:skill_source_id, :skill_version_id, :sha, 'COMMIT', :fingerprint, :imported_by)
                """,
                {
                    "skill_source_id": skill_source_id,
                    "skill_version_id": version_id,
                    "sha": "c" * 40,
                    "fingerprint": "d" * 64,
                    "imported_by": user_id,
                },
            )

            await connection.execute(text("DELETE FROM skill_version WHERE id = :id"), {"id": version_id})
            remaining = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM local_oss_skill_version_source WHERE skill_version_id = :id"
                        ),
                        {"id": version_id},
                    )
                ).scalar_one()
            )
            assert remaining == 0
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM skill WHERE namespace_id IN (SELECT id FROM namespace WHERE slug = :slug)"),
                {"slug": namespace_slug},
            )
            await connection.execute(text("DELETE FROM namespace WHERE slug = :slug"), {"slug": namespace_slug})
            await connection.execute(text("DELETE FROM user_account WHERE id = :id"), {"id": user_id})
        await engine.dispose()
