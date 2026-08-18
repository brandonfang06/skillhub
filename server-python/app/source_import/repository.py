from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.source_import.service import IdentityAccount, NamespaceRecord, NamespaceSourceBinding


class SourceImportRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def read_identity_accounts(self, provider_code: str, login_name: str) -> list[IdentityAccount]:
        rows = (
            await self.connection.execute(
                text(
                    """
                    SELECT ua.id AS user_id,
                           ua.display_name,
                           ua.status,
                           ib.provider_code,
                           ib.login_name
                    FROM identity_binding ib
                    JOIN user_account ua ON ua.id = ib.user_id
                    WHERE ib.provider_code = :provider_code
                      AND ib.login_name = :login_name
                    ORDER BY ua.id ASC
                    """
                ),
                {"provider_code": provider_code, "login_name": login_name},
            )
        ).mappings().all()
        return [_identity_account(dict(row)) for row in rows]

    async def read_namespace(self, slug: str) -> NamespaceRecord | None:
        row = (
            await self.connection.execute(
                text(
                    """
                    SELECT id, slug, display_name, type, status
                    FROM namespace
                    WHERE slug = :slug
                    LIMIT 1
                    """
                ),
                {"slug": slug},
            )
        ).mappings().one_or_none()
        return _namespace_record(dict(row)) if row is not None else None

    async def read_namespace_source_by_repository(self, repository_url: str) -> NamespaceSourceBinding | None:
        row = (
            await self.connection.execute(
                text(
                    """
                    SELECT id, namespace_id, repository_url
                    FROM local_oss_namespace_source
                    WHERE repository_url = :repository_url
                    LIMIT 1
                    """
                ),
                {"repository_url": repository_url},
            )
        ).mappings().one_or_none()
        return _namespace_source_binding(dict(row)) if row is not None else None

    async def read_namespace_source_by_namespace(self, namespace_id: int) -> NamespaceSourceBinding | None:
        row = (
            await self.connection.execute(
                text(
                    """
                    SELECT id, namespace_id, repository_url
                    FROM local_oss_namespace_source
                    WHERE namespace_id = :namespace_id
                    LIMIT 1
                    """
                ),
                {"namespace_id": namespace_id},
            )
        ).mappings().one_or_none()
        return _namespace_source_binding(dict(row)) if row is not None else None

    async def read_namespace_owners(self, namespace_id: int) -> list[IdentityAccount]:
        rows = (
            await self.connection.execute(
                text(
                    """
                    SELECT ua.id AS user_id,
                           ua.display_name,
                           ua.status,
                           identity.provider_code,
                           identity.login_name
                    FROM namespace_member nm
                    JOIN user_account ua ON ua.id = nm.user_id
                    LEFT JOIN LATERAL (
                        SELECT ib.provider_code, ib.login_name
                        FROM identity_binding ib
                        WHERE ib.user_id = ua.id
                        ORDER BY CASE WHEN ib.provider_code = 'keycloak' THEN 0 ELSE 1 END,
                                 ib.id ASC
                        LIMIT 1
                    ) identity ON TRUE
                    WHERE nm.namespace_id = :namespace_id
                      AND nm.role = 'OWNER'
                    ORDER BY ua.id ASC
                    """
                ),
                {"namespace_id": namespace_id},
            )
        ).mappings().all()
        return [_identity_account(dict(row)) for row in rows]

    async def create_namespace_source(
        self,
        *,
        slug: str,
        display_name: str,
        repository_url: str,
        owner: IdentityAccount,
        actor_user_id: str,
        request_id: str | None,
    ) -> tuple[NamespaceRecord, NamespaceSourceBinding]:
        namespace_row = (
            await self.connection.execute(
                text(
                    """
                    INSERT INTO namespace (slug, display_name, type, status, created_by)
                    VALUES (:slug, :display_name, 'TEAM', 'ACTIVE', :created_by)
                    RETURNING id, slug, display_name, type, status
                    """
                ),
                {"slug": slug, "display_name": display_name, "created_by": actor_user_id},
            )
        ).mappings().one()
        namespace = _namespace_record(dict(namespace_row))
        await self.connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :user_id, 'OWNER')
                """
            ),
            {"namespace_id": namespace.id, "user_id": owner.user_id},
        )
        binding_row = (
            await self.connection.execute(
                text(
                    """
                    INSERT INTO local_oss_namespace_source (namespace_id, repository_url, created_by)
                    VALUES (:namespace_id, :repository_url, :created_by)
                    RETURNING id, namespace_id, repository_url
                    """
                ),
                {
                    "namespace_id": namespace.id,
                    "repository_url": repository_url,
                    "created_by": actor_user_id,
                },
            )
        ).mappings().one()
        binding = _namespace_source_binding(dict(binding_row))
        await write_audit_log(
            self.connection,
            actor_user_id=actor_user_id,
            action="CREATE_OSS_SOURCE_NAMESPACE",
            target_type="NAMESPACE",
            target_id=namespace.id,
            request_id=request_id,
            client_ip=None,
            user_agent=None,
            detail={
                "repositoryUrl": repository_url,
                "namespaceSlug": slug,
                "ownerUserId": owner.user_id,
            },
            created_at=datetime.now(UTC),
        )
        return namespace, binding


def _identity_account(row: dict[str, Any]) -> IdentityAccount:
    return IdentityAccount(
        user_id=str(row["user_id"]),
        display_name=str(row["display_name"]),
        status=str(row["status"]),
        provider_code=str(row["provider_code"]) if row.get("provider_code") is not None else None,
        login_name=str(row["login_name"]) if row.get("login_name") is not None else None,
    )


def _namespace_record(row: dict[str, Any]) -> NamespaceRecord:
    return NamespaceRecord(
        id=int(row["id"]),
        slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        type=str(row["type"]),
        status=str(row["status"]),
    )


def _namespace_source_binding(row: dict[str, Any]) -> NamespaceSourceBinding:
    return NamespaceSourceBinding(
        id=int(row["id"]),
        namespace_id=int(row["namespace_id"]),
        repository_url=str(row["repository_url"]),
    )
