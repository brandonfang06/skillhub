from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.skills.read_repository import read_skill_version_detail

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.anyio
@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="SKILLHUB_TEST_DATABASE_URL is required",
)
async def test_version_detail_resolves_native_and_oss_submitters_without_changing_owner() -> None:
    suffix = uuid4().hex[:12]
    owner_id = f"attribution-owner-{suffix}"
    native_submitter_id = f"attribution-native-{suffix}"
    importer_id = f"attribution-importer-{suffix}"
    service_id = f"svc_attribution_{suffix}"
    namespace_slug = f"attribution-{suffix}"
    repository_url = f"https://github.com/attribution-{suffix}/skills"
    commit_sha = "a" * 40
    created_at = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_id: int | None = None
    skill_id: int | None = None

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES
                        (:owner_id, 'Alice Owner'),
                        (:native_submitter_id, 'Bob Submitter'),
                        (:importer_id, 'hcfange')
                    """
                ),
                {
                    "owner_id": owner_id,
                    "native_submitter_id": native_submitter_id,
                    "importer_id": importer_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO service_principal (
                        id, code, display_name, status, created_by_user_id
                    )
                    VALUES (:id, :code, 'Attribution importer', 'ACTIVE', :owner_id)
                    """
                ),
                {
                    "id": service_id,
                    "code": f"attribution-{suffix}",
                    "owner_id": owner_id,
                },
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (
                                slug, display_name, type, status, created_by
                            )
                            VALUES (:slug, :display_name, 'TEAM', 'ACTIVE', :owner_id)
                            RETURNING id
                            """
                        ),
                        {
                            "slug": namespace_slug,
                            "display_name": namespace_slug,
                            "owner_id": owner_id,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES (:namespace_id, :owner_id, 'OWNER')
                    """
                ),
                {"namespace_id": namespace_id, "owner_id": owner_id},
            )
            skill_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill (
                                namespace_id, slug, display_name, summary, owner_id,
                                visibility, status, created_by, updated_by
                            )
                            VALUES (
                                :namespace_id, 'demo-skill', 'Demo Skill', 'summary',
                                :owner_id, 'PUBLIC', 'ACTIVE', :owner_id, :owner_id
                            )
                            RETURNING id
                            """
                        ),
                        {"namespace_id": namespace_id, "owner_id": owner_id},
                    )
                ).scalar_one()
            )
            native_version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (
                                skill_id, version, status, published_at, created_by,
                                created_at, bundle_ready, download_ready
                            )
                            VALUES (
                                :skill_id, '1.0.0', 'PUBLISHED', :created_at, :owner_id,
                                :created_at, TRUE, TRUE
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "skill_id": skill_id,
                            "owner_id": owner_id,
                            "created_at": created_at,
                        },
                    )
                ).scalar_one()
            )
            imported_version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (
                                skill_id, version, status, published_at, created_by,
                                created_at, bundle_ready, download_ready
                            )
                            VALUES (
                                :skill_id, '2.0.0', 'PUBLISHED', :created_at, :owner_id,
                                :created_at, TRUE, TRUE
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "skill_id": skill_id,
                            "owner_id": owner_id,
                            "created_at": created_at,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text("UPDATE skill SET latest_version_id = :version_id WHERE id = :skill_id"),
                {"version_id": imported_version_id, "skill_id": skill_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO review_task (
                        skill_version_id, namespace_id, status, submitted_by,
                        submitted_at, reviewed_by, reviewed_at
                    )
                    VALUES
                        (
                            :native_version_id, :namespace_id, 'APPROVED',
                            :native_submitter_id, :created_at, :owner_id, :created_at
                        ),
                        (
                            :imported_version_id, :namespace_id, 'APPROVED',
                            :importer_id, :created_at, :owner_id, :created_at
                        )
                    """
                ),
                {
                    "native_version_id": native_version_id,
                    "imported_version_id": imported_version_id,
                    "namespace_id": namespace_id,
                    "native_submitter_id": native_submitter_id,
                    "importer_id": importer_id,
                    "owner_id": owner_id,
                    "created_at": created_at,
                },
            )
            namespace_source_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO local_oss_namespace_source (
                                namespace_id, repository_url, created_by
                            )
                            VALUES (:namespace_id, :repository_url, :owner_id)
                            RETURNING id
                            """
                        ),
                        {
                            "namespace_id": namespace_id,
                            "repository_url": repository_url,
                            "owner_id": owner_id,
                        },
                    )
                ).scalar_one()
            )
            skill_source_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO local_oss_skill_source (
                                namespace_source_id, source_path, skill_id, created_by
                            )
                            VALUES (
                                :namespace_source_id, 'skills/demo', :skill_id, :owner_id
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "namespace_source_id": namespace_source_id,
                            "skill_id": skill_id,
                            "owner_id": owner_id,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO local_oss_skill_version_source (
                        skill_source_id, skill_version_id, repository_revision_sha,
                        source_ref_type, source_ref, content_fingerprint, imported_by,
                        imported_at, imported_by_service_principal_id
                    )
                    VALUES (
                        :skill_source_id, :skill_version_id, :commit_sha,
                        'BRANCH', 'main', :fingerprint, :importer_id,
                        :created_at, :service_id
                    )
                    """
                ),
                {
                    "skill_source_id": skill_source_id,
                    "skill_version_id": imported_version_id,
                    "commit_sha": commit_sha,
                    "fingerprint": "b" * 64,
                    "importer_id": importer_id,
                    "created_at": created_at,
                    "service_id": service_id,
                },
            )

        native = await read_skill_version_detail(
            engine,
            namespace_slug,
            "demo-skill",
            "1.0.0",
        )
        imported = await read_skill_version_detail(
            engine,
            namespace_slug,
            "demo-skill",
            "2.0.0",
        )

        assert native["versionAttribution"] == {
            "type": "NATIVE_SUBMISSION",
            "submittedBy": native_submitter_id,
            "submittedByName": "Bob Submitter",
            "submittedAt": "2026-08-19T08:00:00Z",
        }
        assert imported["versionAttribution"] == {
            "type": "OSS_IMPORT",
            "submittedBy": importer_id,
            "submittedByName": "hcfange",
            "submittedAt": "2026-08-19T08:00:00Z",
        }
        assert imported["sourceProvenance"]["repositoryRevisionSha"] == commit_sha

        async with engine.connect() as connection:
            stored_owner = (
                await connection.execute(
                    text("SELECT owner_id FROM skill WHERE id = :skill_id"),
                    {"skill_id": skill_id},
                )
            ).scalar_one()
        assert str(stored_owner) == owner_id
    finally:
        async with engine.begin() as connection:
            if skill_id is not None:
                await connection.execute(
                    text("UPDATE skill SET latest_version_id = NULL WHERE id = :skill_id"),
                    {"skill_id": skill_id},
                )
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM review_task WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text(
                        """
                        DELETE FROM skill_version
                        WHERE skill_id IN (
                            SELECT id FROM skill WHERE namespace_id = :namespace_id
                        )
                        """
                    ),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM skill WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
            await connection.execute(
                text("DELETE FROM service_principal WHERE id = :service_id"),
                {"service_id": service_id},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM user_account
                    WHERE id IN (:owner_id, :native_submitter_id, :importer_id)
                    """
                ),
                {
                    "owner_id": owner_id,
                    "native_submitter_id": native_submitter_id,
                    "importer_id": importer_id,
                },
            )
        await engine.dispose()
