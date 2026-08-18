from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.source_import.contracts import SourceIdentity
from app.source_import.repository import SourceImportRepository
from app.source_import.service import EnsureSourceNamespaceInput, ensure_source_namespace
from app.source_import.source import canonicalize_github_repository


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


class FailingAfterNamespaceRepository(SourceImportRepository):
    async def create_namespace_source(self, **kwargs: object):  # type: ignore[no-untyped-def]
        await super().create_namespace_source(**kwargs)  # type: ignore[arg-type]
        raise RuntimeError("forced failure after namespace source binding")


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_source_namespace_creation_is_atomic_and_reuses_current_owner() -> None:
    suffix = uuid4().hex[:12]
    actor_id = f"oss-actor-{suffix}"
    owner_id = f"oss-owner-{suffix}"
    owner_login = f"owner-{suffix}"
    repository = canonicalize_github_repository(f"https://github.com/owner{suffix}/repo")
    failing_repository = canonicalize_github_repository(f"https://github.com/owner{suffix}/fail")
    engine = create_async_engine(str(TEST_DATABASE_URL))

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES (:actor_id, 'OSS importer actor'), (:owner_id, 'OSS namespace owner')
                    """
                ),
                {"actor_id": actor_id, "owner_id": owner_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO identity_binding (user_id, provider_code, subject, login_name)
                    VALUES (:owner_id, 'keycloak', :subject, :login_name)
                    """
                ),
                {"owner_id": owner_id, "subject": f"subject-{suffix}", "login_name": owner_login},
            )

        request = EnsureSourceNamespaceInput(
            repository=repository,
            requested_display_name=repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            actor_user_id=actor_id,
            request_id=f"request-{suffix}",
        )
        created = await ensure_source_namespace(engine, request)
        existing = await ensure_source_namespace(
            engine,
            EnsureSourceNamespaceInput(
                repository=repository,
                requested_display_name=repository.namespace_display_name,
                fallback_owner=SourceIdentity("keycloak", "not-used-for-existing"),
                actor_user_id=actor_id,
            ),
        )

        assert created.outcome == "CREATED"
        assert existing.outcome == "EXISTING"
        assert existing.owner.user_id == owner_id
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT n.type, n.status, nm.role, source.repository_url
                        FROM namespace n
                        JOIN namespace_member nm ON nm.namespace_id = n.id
                        JOIN local_oss_namespace_source source ON source.namespace_id = n.id
                        WHERE n.slug = :slug
                        """
                    ),
                    {"slug": repository.namespace_slug},
                )
            ).mappings().one()
            assert dict(row) == {
                "type": "TEAM",
                "status": "ACTIVE",
                "role": "OWNER",
                "repository_url": repository.canonical_url,
            }

        failing_request = EnsureSourceNamespaceInput(
            repository=failing_repository,
            requested_display_name=failing_repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            actor_user_id=actor_id,
        )
        with pytest.raises(RuntimeError, match="forced failure"):
            await ensure_source_namespace(
                engine,
                failing_request,
                repository_factory=FailingAfterNamespaceRepository,
            )

        async with engine.connect() as connection:
            rolled_back = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM namespace WHERE slug = :slug"),
                        {"slug": failing_repository.namespace_slug},
                    )
                ).scalar_one()
            )
            assert rolled_back == 0
    finally:
        async with engine.begin() as connection:
            namespace_ids = (
                await connection.execute(
                    text("SELECT id FROM namespace WHERE slug IN (:slug, :failing_slug)"),
                    {"slug": repository.namespace_slug, "failing_slug": failing_repository.namespace_slug},
                )
            ).scalars().all()
            if namespace_ids:
                await connection.execute(
                    text("DELETE FROM namespace_member WHERE namespace_id = ANY(:namespace_ids)"),
                    {"namespace_ids": list(namespace_ids)},
                )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = ANY(:namespace_ids)"),
                    {"namespace_ids": list(namespace_ids)},
                )
            await connection.execute(
                text("DELETE FROM audit_log WHERE actor_user_id IN (:actor_id, :owner_id)"),
                {"actor_id": actor_id, "owner_id": owner_id},
            )
            await connection.execute(
                text("DELETE FROM identity_binding WHERE user_id IN (:actor_id, :owner_id)"),
                {"actor_id": actor_id, "owner_id": owner_id},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id IN (:actor_id, :owner_id)"),
                {"actor_id": actor_id, "owner_id": owner_id},
            )
        await engine.dispose()
