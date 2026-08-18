from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.publish.package import PackageEntry
from app.source_import.contracts import SourceIdentity, SourceServiceActor
from app.source_import.repository import SourceImportRepository
from app.source_import.service import (
    ValidateSourceSkillInput,
    validate_source_skill_in_transaction,
)
from app.source_import.source import (
    canonicalize_github_repository,
    validate_source_revision,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


def _entries() -> list[PackageEntry]:
    return [
        PackageEntry(
            "SKILL.md",
            b"---\nname: Database Skill\ndescription: PostgreSQL validation\n---\n# Database Skill\n",
            "text/markdown",
        )
    ]


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_source_validation_reads_real_namespace_identity_and_membership_state() -> None:
    suffix = uuid4().hex[:12]
    actor_id = f"validation-actor-{suffix}"
    owner_id = f"validation-owner-{suffix}"
    trigger_id = f"validation-trigger-{suffix}"
    trigger_login = f"validation-login-{suffix}"
    source = canonicalize_github_repository(f"https://github.com/valid{suffix}/repo")
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_id: int | None = None

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES
                        (:actor_id, 'Validation actor'),
                        (:owner_id, 'Validation owner'),
                        (:trigger_id, 'Validation trigger')
                    """
                ),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO identity_binding (user_id, provider_code, subject, login_name)
                    VALUES (:trigger_id, 'keycloak', :subject, :login_name)
                    """
                ),
                {"trigger_id": trigger_id, "subject": f"trigger-subject-{suffix}", "login_name": trigger_login},
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (slug, display_name, type, status, created_by)
                            VALUES (:slug, :display_name, 'TEAM', 'ACTIVE', :actor_id)
                            RETURNING id
                            """
                        ),
                        {
                            "slug": source.namespace_slug,
                            "display_name": source.namespace_display_name,
                            "actor_id": actor_id,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text("INSERT INTO namespace_member (namespace_id, user_id, role) VALUES (:id, :owner_id, 'OWNER')"),
                {"id": namespace_id, "owner_id": owner_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO local_oss_namespace_source (namespace_id, repository_url, created_by)
                    VALUES (:namespace_id, :repository_url, :actor_id)
                    """
                ),
                {"namespace_id": namespace_id, "repository_url": source.canonical_url, "actor_id": actor_id},
            )

        async with engine.connect() as connection:
            plan = await validate_source_skill_in_transaction(
                SourceImportRepository(connection),
                ValidateSourceSkillInput(
                    namespace_slug=source.namespace_slug,
                    repository=source,
                    revision=validate_source_revision("a" * 40, "COMMIT", None),
                    source_path="skills/database-skill",
                    entries=_entries(),
                    version_override="git-" + "a" * 40,
                    initiator=SourceIdentity("keycloak", trigger_login),
                    service_actor=SourceServiceActor(
                        f"svc_{suffix}", f"validation-{suffix}", "Validation service"
                    ),
                ),
            )

        assert plan.outcome == "IMPORT"
        assert plan.stable_owner.user_id == trigger_id
        assert plan.review_submitter.user_id == trigger_id
        assert plan.add_submitter_as_member is True
    finally:
        async with engine.begin() as connection:
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = :id"),
                    {"id": namespace_id},
                )
                await connection.execute(text("DELETE FROM namespace WHERE id = :id"), {"id": namespace_id})
            await connection.execute(
                text("DELETE FROM identity_binding WHERE user_id IN (:actor_id, :owner_id, :trigger_id)"),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id IN (:actor_id, :owner_id, :trigger_id)"),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
        await engine.dispose()
