from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.source_import.contracts import SourceIdentity, SourceServiceActor
from app.source_import.repository import SourceImportRepository
from app.source_import.service import (
    EnsureSourceNamespaceInput,
    SourceImportConflict,
    ensure_source_namespace,
)
from app.source_import.source import canonicalize_github_repository

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


class FailingAfterNamespaceRepository(SourceImportRepository):
    async def create_namespace_source(self, **kwargs: object):  # type: ignore[no-untyped-def]
        await super().create_namespace_source(**kwargs)  # type: ignore[arg-type]
        raise RuntimeError("forced failure after namespace source binding")


class PausingAfterMissingNamespaceRepository(SourceImportRepository):
    def __init__(
        self,
        connection: object,
        missing_namespace_read: asyncio.Event,
        release_creation: asyncio.Event,
    ) -> None:
        super().__init__(connection)
        self.missing_namespace_read = missing_namespace_read
        self.release_creation = release_creation

    async def read_namespace(self, slug: str):  # type: ignore[no-untyped-def]
        namespace = await super().read_namespace(slug)
        if namespace is None and not self.missing_namespace_read.is_set():
            self.missing_namespace_read.set()
            await self.release_creation.wait()
        return namespace


class PausingAfterPlatformAdminRepository(SourceImportRepository):
    def __init__(
        self,
        connection: object,
        platform_admin_read: asyncio.Event,
        release_creation: asyncio.Event,
    ) -> None:
        super().__init__(connection)
        self.platform_admin_read = platform_admin_read
        self.release_creation = release_creation

    async def read_service_principal_platform_admin(self, service_principal_id: str):  # type: ignore[no-untyped-def]
        platform_admin = await super().read_service_principal_platform_admin(
            service_principal_id
        )
        self.platform_admin_read.set()
        await self.release_creation.wait()
        return platform_admin


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_source_namespace_creation_is_atomic_and_reuses_current_owner() -> None:
    suffix = uuid4().hex[:12]
    actor_id = f"oss-actor-{suffix}"
    service_id = f"svc_{suffix}"
    invalid_service_id = f"svc_invalid_{suffix}"
    inactive_service_id = f"svc_inactive_{suffix}"
    owner_service_id = f"svc_owner_{suffix}"
    owner_id = f"oss-owner-{suffix}"
    admin_id = f"oss-admin-{suffix}"
    inactive_admin_id = f"oss-inactive-admin-{suffix}"
    ordinary_user_id = f"oss-user-{suffix}"
    owner_login = f"owner-{suffix}"
    repository = canonicalize_github_repository(f"https://github.com/owner{suffix}/repo")
    failing_repository = canonicalize_github_repository(f"https://github.com/owner{suffix}/fail")
    invalid_admin_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/invalid-admin"
    )
    inactive_admin_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/inactive-admin"
    )
    same_owner_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/same-owner"
    )
    concurrent_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/concurrent"
    )
    authorization_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/authorization-lock"
    )
    authorization_role_repository = canonicalize_github_repository(
        f"https://github.com/owner{suffix}/authorization-role-lock"
    )
    engine = create_async_engine(str(TEST_DATABASE_URL))

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name)
                    VALUES (:actor_id, 'OSS importer actor'),
                           (:owner_id, 'OSS namespace owner'),
                           (:admin_id, 'OSS platform admin'),
                           (:inactive_admin_id, 'Inactive platform admin'),
                           (:ordinary_user_id, 'Ordinary user')
                    """
                ),
                {
                    "actor_id": actor_id,
                    "owner_id": owner_id,
                    "admin_id": admin_id,
                    "inactive_admin_id": inactive_admin_id,
                    "ordinary_user_id": ordinary_user_id,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE user_account
                    SET status = 'DISABLED'
                    WHERE id = :inactive_admin_id
                    """
                ),
                {"inactive_admin_id": inactive_admin_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO user_role_binding (user_id, role_id)
                    SELECT user_id, role.id
                    FROM unnest(CAST(:user_ids AS VARCHAR[])) AS users(user_id)
                    CROSS JOIN role
                    WHERE role.code = 'SUPER_ADMIN'
                    """
                ),
                {"user_ids": [actor_id, owner_id, admin_id, inactive_admin_id]},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO service_principal (
                        id, code, display_name, status, created_by_user_id
                    )
                    VALUES (:service_id, :code, 'OSS importer service', 'ACTIVE', :actor_id),
                           (:invalid_service_id, :invalid_code, 'Invalid importer service',
                            'ACTIVE', :ordinary_user_id),
                           (:inactive_service_id, :inactive_code, 'Inactive admin service',
                            'ACTIVE', :inactive_admin_id),
                           (:owner_service_id, :owner_code, 'Owner admin service',
                            'ACTIVE', :owner_id)
                    """
                ),
                {
                    "service_id": service_id,
                    "code": f"oss-{suffix}",
                    "actor_id": actor_id,
                    "invalid_service_id": invalid_service_id,
                    "invalid_code": f"invalid-oss-{suffix}",
                    "ordinary_user_id": ordinary_user_id,
                    "inactive_service_id": inactive_service_id,
                    "inactive_code": f"inactive-oss-{suffix}",
                    "inactive_admin_id": inactive_admin_id,
                    "owner_service_id": owner_service_id,
                    "owner_code": f"owner-oss-{suffix}",
                    "owner_id": owner_id,
                },
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
            service_actor=SourceServiceActor(service_id, f"oss-{suffix}", "OSS importer service"),
            request_id=f"request-{suffix}",
        )
        created = await ensure_source_namespace(engine, request)
        existing = await ensure_source_namespace(
            engine,
            EnsureSourceNamespaceInput(
                repository=repository,
                requested_display_name=repository.namespace_display_name,
                fallback_owner=SourceIdentity("keycloak", "not-used-for-existing"),
                service_actor=SourceServiceActor(service_id, f"oss-{suffix}", "OSS importer service"),
            ),
        )

        assert created.outcome == "CREATED"
        assert existing.outcome == "EXISTING"
        assert existing.owner.user_id == owner_id
        async with engine.connect() as connection:
            namespace_row = (
                await connection.execute(
                    text(
                        """
                        SELECT n.type, n.status, n.created_by AS namespace_created_by,
                               source.repository_url, source.created_by AS source_created_by,
                               source.created_by_service_principal_id
                        FROM namespace n
                        JOIN local_oss_namespace_source source ON source.namespace_id = n.id
                        WHERE n.slug = :slug
                        """
                    ),
                    {"slug": repository.namespace_slug},
                )
            ).mappings().one()
            assert dict(namespace_row) == {
                "type": "TEAM",
                "status": "ACTIVE",
                "namespace_created_by": owner_id,
                "repository_url": repository.canonical_url,
                "source_created_by": owner_id,
                "created_by_service_principal_id": service_id,
            }
            memberships = (
                await connection.execute(
                    text(
                        """
                        SELECT nm.user_id, nm.role
                        FROM namespace_member nm
                        JOIN namespace n ON n.id = nm.namespace_id
                        WHERE n.slug = :slug
                        ORDER BY nm.user_id
                        """
                    ),
                    {"slug": repository.namespace_slug},
                )
            ).mappings().all()
            assert [dict(row) for row in memberships] == sorted(
                [
                    {"user_id": owner_id, "role": "OWNER"},
                    {"user_id": actor_id, "role": "ADMIN"},
                ],
                key=lambda row: row["user_id"],
            )
            audit_detail = (
                await connection.execute(
                    text(
                        """
                        SELECT detail_json
                        FROM audit_log
                        WHERE actor_service_principal_id = :service_id
                          AND action = 'CREATE_OSS_SOURCE_NAMESPACE'
                          AND target_id = (
                              SELECT id FROM namespace WHERE slug = :slug
                          )
                        """
                    ),
                    {"service_id": service_id, "slug": repository.namespace_slug},
                )
            ).scalar_one()
            assert audit_detail["outcome"] == "CREATED"
            assert audit_detail["platformAdminUserId"] == actor_id

        invalid_admin_cases = [
            (
                invalid_admin_repository,
                SourceServiceActor(
                    invalid_service_id,
                    f"invalid-oss-{suffix}",
                    "Invalid importer service",
                ),
                "error.sourceImport.platformAdmin.invalid",
            ),
            (
                inactive_admin_repository,
                SourceServiceActor(
                    inactive_service_id,
                    f"inactive-oss-{suffix}",
                    "Inactive admin service",
                ),
                "error.sourceImport.platformAdmin.invalid",
            ),
            (
                same_owner_repository,
                SourceServiceActor(
                    owner_service_id,
                    f"owner-oss-{suffix}",
                    "Owner admin service",
                ),
                "error.sourceImport.platformAdmin.sameAsOwner",
            ),
        ]
        for invalid_repository, invalid_actor, expected_code in invalid_admin_cases:
            invalid_admin_request = EnsureSourceNamespaceInput(
                repository=invalid_repository,
                requested_display_name=invalid_repository.namespace_display_name,
                fallback_owner=SourceIdentity("keycloak", owner_login),
                service_actor=invalid_actor,
            )
            with pytest.raises(SourceImportConflict) as invalid_admin_error:
                await ensure_source_namespace(engine, invalid_admin_request)
            assert invalid_admin_error.value.code == expected_code

        async with engine.connect() as connection:
            invalid_namespace_count = int(
                (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM namespace WHERE slug = ANY(:slugs)"),
                        {
                            "slugs": [
                                invalid_admin_repository.namespace_slug,
                                inactive_admin_repository.namespace_slug,
                                same_owner_repository.namespace_slug,
                            ]
                        },
                    )
                ).scalar_one()
            )
            assert invalid_namespace_count == 0

        concurrent_request = EnsureSourceNamespaceInput(
            repository=concurrent_repository,
            requested_display_name=concurrent_repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            service_actor=SourceServiceActor(
                service_id, f"oss-{suffix}", "OSS importer service"
            ),
        )
        missing_namespace_read = asyncio.Event()
        release_creation = asyncio.Event()

        def pausing_repository(connection: object) -> SourceImportRepository:
            return PausingAfterMissingNamespaceRepository(
                connection, missing_namespace_read, release_creation
            )

        first_ensure = asyncio.create_task(
            ensure_source_namespace(
                engine,
                concurrent_request,
                repository_factory=pausing_repository,
            )
        )
        await asyncio.wait_for(missing_namespace_read.wait(), timeout=2)
        with pytest.raises(SourceImportConflict) as concurrent_error:
            await ensure_source_namespace(engine, concurrent_request)
        assert (
            concurrent_error.value.code
            == "error.sourceImport.namespace.creationInProgress"
        )
        release_creation.set()
        first_result = await first_ensure
        retry_result = await ensure_source_namespace(engine, concurrent_request)

        assert first_result.outcome == "CREATED"
        assert retry_result.outcome == "EXISTING"

        failing_request = EnsureSourceNamespaceInput(
            repository=failing_repository,
            requested_display_name=failing_repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            service_actor=SourceServiceActor(service_id, f"oss-{suffix}", "OSS importer service"),
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
            rolled_back_audit = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM audit_log
                            WHERE actor_service_principal_id = :service_id
                              AND action = 'CREATE_OSS_SOURCE_NAMESPACE'
                              AND detail_json ->> 'repositoryUrl' = :repository_url
                            """
                        ),
                        {
                            "service_id": service_id,
                            "repository_url": failing_repository.canonical_url,
                        },
                    )
                ).scalar_one()
            )
            assert rolled_back_audit == 0

        authorization_request = EnsureSourceNamespaceInput(
            repository=authorization_repository,
            requested_display_name=authorization_repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            service_actor=SourceServiceActor(
                service_id, f"oss-{suffix}", "OSS importer service"
            ),
        )
        platform_admin_read = asyncio.Event()
        release_authorization_creation = asyncio.Event()

        def authorization_repository_factory(
            connection: object,
        ) -> SourceImportRepository:
            return PausingAfterPlatformAdminRepository(
                connection,
                platform_admin_read,
                release_authorization_creation,
            )

        authorization_ensure = asyncio.create_task(
            ensure_source_namespace(
                engine,
                authorization_request,
                repository_factory=authorization_repository_factory,
            )
        )
        await asyncio.wait_for(platform_admin_read.wait(), timeout=2)

        async def disable_platform_admin() -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE user_account SET status = 'DISABLED' "
                        "WHERE id = :user_id"
                    ),
                    {"user_id": actor_id},
                )

        disable_task = asyncio.create_task(disable_platform_admin())
        await asyncio.sleep(0.1)
        disable_waited_for_creation = not disable_task.done()
        release_authorization_creation.set()
        authorization_result, _ = await asyncio.gather(
            authorization_ensure, disable_task
        )

        assert disable_waited_for_creation
        assert authorization_result.outcome == "CREATED"

        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE user_account SET status = 'ACTIVE' WHERE id = :user_id"),
                {"user_id": actor_id},
            )

        authorization_role_request = EnsureSourceNamespaceInput(
            repository=authorization_role_repository,
            requested_display_name=authorization_role_repository.namespace_display_name,
            fallback_owner=SourceIdentity("keycloak", owner_login),
            service_actor=SourceServiceActor(
                service_id, f"oss-{suffix}", "OSS importer service"
            ),
        )
        role_platform_admin_read = asyncio.Event()
        release_role_authorization_creation = asyncio.Event()

        def role_authorization_repository_factory(
            connection: object,
        ) -> SourceImportRepository:
            return PausingAfterPlatformAdminRepository(
                connection,
                role_platform_admin_read,
                release_role_authorization_creation,
            )

        role_authorization_ensure = asyncio.create_task(
            ensure_source_namespace(
                engine,
                authorization_role_request,
                repository_factory=role_authorization_repository_factory,
            )
        )
        await asyncio.wait_for(role_platform_admin_read.wait(), timeout=2)

        async def revoke_platform_admin() -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        DELETE FROM user_role_binding
                        WHERE user_id = :user_id
                          AND role_id = (
                              SELECT id FROM role WHERE code = 'SUPER_ADMIN'
                          )
                        """
                    ),
                    {"user_id": actor_id},
                )

        revoke_task = asyncio.create_task(revoke_platform_admin())
        await asyncio.sleep(0.1)
        revoke_waited_for_creation = not revoke_task.done()
        release_role_authorization_creation.set()
        role_authorization_result, _ = await asyncio.gather(
            role_authorization_ensure, revoke_task
        )

        assert revoke_waited_for_creation
        assert role_authorization_result.outcome == "CREATED"
    finally:
        async with engine.begin() as connection:
            namespace_ids = (
                await connection.execute(
                    text("SELECT id FROM namespace WHERE slug = ANY(:slugs)"),
                    {
                        "slugs": [
                            repository.namespace_slug,
                            failing_repository.namespace_slug,
                            invalid_admin_repository.namespace_slug,
                            inactive_admin_repository.namespace_slug,
                            same_owner_repository.namespace_slug,
                            concurrent_repository.namespace_slug,
                            authorization_repository.namespace_slug,
                            authorization_role_repository.namespace_slug,
                        ]
                    },
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
                text(
                    "DELETE FROM audit_log WHERE actor_service_principal_id = :service_id OR actor_user_id = :owner_id"
                ),
                {"service_id": service_id, "owner_id": owner_id},
            )
            await connection.execute(
                text("DELETE FROM service_principal WHERE id = ANY(:service_ids)"),
                {
                    "service_ids": [
                        service_id,
                        invalid_service_id,
                        inactive_service_id,
                        owner_service_id,
                    ]
                },
            )
            await connection.execute(
                text("DELETE FROM user_role_binding WHERE user_id = ANY(:user_ids)"),
                {"user_ids": [actor_id, owner_id, admin_id, inactive_admin_id]},
            )
            await connection.execute(
                text("DELETE FROM identity_binding WHERE user_id IN (:actor_id, :owner_id)"),
                {"actor_id": actor_id, "owner_id": owner_id},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = ANY(:user_ids)"),
                {
                    "user_ids": [
                        actor_id,
                        owner_id,
                        admin_id,
                        inactive_admin_id,
                        ordinary_user_id,
                    ]
                },
            )
        await engine.dispose()
