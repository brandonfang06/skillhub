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
    SourceSkillSubmissionRuntime,
    ValidateSourceSkillInput,
    submit_source_skill,
)
from app.source_import.source import (
    canonicalize_github_repository,
    validate_source_revision,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


class FailingPersistenceRepository(SourceImportRepository):
    async def persist_source_submission(self, **kwargs: object) -> None:
        await super().persist_source_submission(**kwargs)  # type: ignore[arg-type]
        raise RuntimeError("forced provenance transaction failure")


def _entries(name: str = "Imported Skill") -> list[PackageEntry]:
    return [
        PackageEntry(
            "SKILL.md",
            (
                "---\n"
                f"name: {name}\n"
                "description: Imported through GitLab\n"
                "---\n"
                f"# {name}\n"
            ).encode(),
            "text/markdown",
        )
    ]


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_source_submission_persists_owner_submitter_actor_review_and_provenance_atomically(tmp_path) -> None:
    suffix = uuid4().hex[:12]
    actor_id = f"submission-actor-{suffix}"
    service_id = f"svc_{suffix}"
    service_code = f"submission-{suffix}"
    owner_id = f"submission-owner-{suffix}"
    trigger_id = f"submission-trigger-{suffix}"
    trigger_login = f"submission-login-{suffix}"
    source = canonicalize_github_repository(f"https://github.com/submit{suffix}/repo")
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_id: int | None = None

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES
                        (:actor_id, 'Submission actor'),
                        (:owner_id, 'Submission namespace owner'),
                        (:trigger_id, 'Submission trigger')
                    """
                ),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO service_principal (
                        id, code, display_name, status, created_by_user_id
                    )
                    VALUES (:service_id, :service_code, 'Submission service', 'ACTIVE', :actor_id)
                    """
                ),
                {
                    "service_id": service_id,
                    "service_code": service_code,
                    "actor_id": actor_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO identity_binding (user_id, provider_code, subject, login_name)
                    VALUES (:trigger_id, 'keycloak', :subject, :login_name)
                    """
                ),
                {"trigger_id": trigger_id, "subject": f"submission-subject-{suffix}", "login_name": trigger_login},
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

        request = ValidateSourceSkillInput(
            namespace_slug=source.namespace_slug,
            repository=source,
            revision=validate_source_revision("a" * 40, "BRANCH", "main"),
            source_path="skills/imported-skill",
            entries=_entries(),
            version_override="git-" + "a" * 40,
            initiator=SourceIdentity("keycloak", trigger_login),
            service_actor=SourceServiceActor(service_id, service_code, "Submission service"),
            request_id=f"submission-request-{suffix}",
        )
        runtime = SourceSkillSubmissionRuntime(storage_base_path=str(tmp_path), scanner_enabled=False)
        imported = await submit_source_skill(engine, request, runtime)
        retried = await submit_source_skill(engine, request, runtime)

        assert imported.outcome == "IMPORTED"
        assert imported.version_status == "PENDING_REVIEW"
        assert imported.review_task_id is not None
        assert retried.outcome == "SKIPPED_ALREADY_IMPORTED"

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT skill.owner_id,
                               member.role AS trigger_role,
                               review.submitted_by,
                               provenance.imported_by,
                               provenance.imported_by_service_principal_id,
                               skill_source.created_by,
                               skill_source.created_by_service_principal_id,
                               provenance.repository_revision_sha,
                               provenance.content_fingerprint,
                               audit.actor_user_id,
                               audit.actor_service_principal_id
                        FROM skill
                        JOIN skill_version version ON version.skill_id = skill.id
                        JOIN review_task review ON review.skill_version_id = version.id
                        JOIN namespace_member member
                          ON member.namespace_id = skill.namespace_id
                         AND member.user_id = :trigger_id
                        JOIN local_oss_skill_version_source provenance
                          ON provenance.skill_version_id = version.id
                        JOIN local_oss_skill_source skill_source
                          ON skill_source.skill_id = skill.id
                        JOIN audit_log audit
                          ON audit.target_type = 'SKILL_VERSION'
                         AND audit.target_id = version.id
                         AND audit.action = 'SOURCE_IMPORT_SKILL_VERSION'
                        WHERE skill.namespace_id = :namespace_id
                          AND skill.slug = 'imported-skill'
                        """
                    ),
                    {"namespace_id": namespace_id, "trigger_id": trigger_id},
                )
            ).mappings().one()
            assert str(row["owner_id"]) == trigger_id
            assert str(row["trigger_role"]) == "MEMBER"
            assert str(row["submitted_by"]) == trigger_id
            assert str(row["imported_by"]) == trigger_id
            assert str(row["imported_by_service_principal_id"]) == service_id
            assert str(row["created_by"]) == trigger_id
            assert str(row["created_by_service_principal_id"]) == service_id
            assert str(row["repository_revision_sha"]).strip() == "a" * 40
            assert len(str(row["content_fingerprint"]).strip()) == 64
            assert row["actor_user_id"] is None
            assert str(row["actor_service_principal_id"]) == service_id

        failing_request = ValidateSourceSkillInput(
            namespace_slug=source.namespace_slug,
            repository=source,
            revision=validate_source_revision("b" * 40, "COMMIT", None),
            source_path="skills/rollback-skill",
            entries=_entries("Rollback Skill"),
            version_override="git-" + "b" * 40,
            initiator=SourceIdentity("keycloak", trigger_login),
            service_actor=SourceServiceActor(service_id, service_code, "Submission service"),
        )
        with pytest.raises(RuntimeError, match="forced provenance"):
            await submit_source_skill(
                engine,
                failing_request,
                runtime,
                repository_factory=FailingPersistenceRepository,
            )

        async with engine.connect() as connection:
            rolled_back = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM skill
                            WHERE namespace_id = :namespace_id
                              AND slug = 'rollback-skill'
                            """
                        ),
                        {"namespace_id": namespace_id},
                    )
                ).scalar_one()
            )
            assert rolled_back == 0
    finally:
        async with engine.begin() as connection:
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM notification WHERE recipient_id IN (:owner_id, :trigger_id)"),
                    {"owner_id": owner_id, "trigger_id": trigger_id},
                )
                await connection.execute(
                    text("DELETE FROM review_task WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                version_ids = (
                    await connection.execute(
                        text(
                            """
                            SELECT version.id
                            FROM skill_version version
                            JOIN skill ON skill.id = version.skill_id
                            WHERE skill.namespace_id = :namespace_id
                            """
                        ),
                        {"namespace_id": namespace_id},
                    )
                ).scalars().all()
                if version_ids:
                    await connection.execute(
                        text("DELETE FROM skill_file WHERE version_id = ANY(:version_ids)"),
                        {"version_ids": list(version_ids)},
                    )
                    await connection.execute(
                        text("DELETE FROM skill_version WHERE id = ANY(:version_ids)"),
                        {"version_ids": list(version_ids)},
                    )
                await connection.execute(
                    text("DELETE FROM skill WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
                await connection.execute(text("DELETE FROM namespace WHERE id = :id"), {"id": namespace_id})
            await connection.execute(
                text(
                    "DELETE FROM audit_log WHERE actor_service_principal_id = :service_id OR actor_user_id IN (:owner_id, :trigger_id)"
                ),
                {"service_id": service_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
            await connection.execute(
                text("DELETE FROM service_principal WHERE id = :service_id"),
                {"service_id": service_id},
            )
            await connection.execute(
                text("DELETE FROM identity_binding WHERE user_id IN (:actor_id, :owner_id, :trigger_id)"),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id IN (:actor_id, :owner_id, :trigger_id)"),
                {"actor_id": actor_id, "owner_id": owner_id, "trigger_id": trigger_id},
            )
        await engine.dispose()
