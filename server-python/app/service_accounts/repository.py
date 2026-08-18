from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.service_accounts.contracts import (
    ServicePrincipal,
    ServicePrincipalSummary,
    ServiceTokenMetadata,
)


def _scopes(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return tuple(str(item) for item in parsed) if isinstance(parsed, list) else ()
    return ()


def _principal(row: dict[str, Any]) -> ServicePrincipal:
    return ServicePrincipal(
        id=str(row["id"]),
        code=str(row["code"]),
        display_name=str(row["display_name"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        created_by_user_id=str(row["created_by_user_id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _token(row: dict[str, Any]) -> ServiceTokenMetadata:
    return ServiceTokenMetadata(
        id=int(row["id"]),
        service_principal_id=str(row["service_principal_id"]),
        name=str(row["name"]),
        token_prefix=str(row["token_prefix"]),
        scopes=_scopes(row.get("scope_json")),
        created_by_user_id=str(row["created_by_user_id"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        last_used_at=row.get("last_used_at"),
        revoked_at=row.get("revoked_at"),
    )


def _principal_summary(row: dict[str, Any]) -> ServicePrincipalSummary:
    principal = _principal(row)
    return ServicePrincipalSummary(
        **principal.__dict__,
        active_token_count=int(row["active_token_count"]),
        nearest_token_expiry=row.get("nearest_token_expiry"),
        last_used_at=row.get("last_used_at"),
    )


class ServiceAccountRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def list_principals(
        self,
        *,
        page: int,
        size: int,
    ) -> tuple[list[ServicePrincipalSummary], int]:
        total = int(
            (
                await self.connection.execute(
                    text("SELECT COUNT(*) FROM service_principal")
                )
            ).scalar_one()
        )
        rows = (
            (
                await self.connection.execute(
                    text(
                        """
                    SELECT principal.*,
                           COUNT(token.id) FILTER (
                               WHERE token.revoked_at IS NULL
                                 AND token.expires_at > CURRENT_TIMESTAMP
                           ) AS active_token_count,
                           MIN(token.expires_at) FILTER (
                               WHERE token.revoked_at IS NULL
                                 AND token.expires_at > CURRENT_TIMESTAMP
                           ) AS nearest_token_expiry,
                           MAX(token.last_used_at) AS last_used_at
                    FROM service_principal principal
                    LEFT JOIN service_token token
                      ON token.service_principal_id = principal.id
                    GROUP BY principal.id
                    ORDER BY principal.created_at DESC, principal.id ASC
                    OFFSET :offset LIMIT :limit
                    """
                    ),
                    {"offset": page * size, "limit": size},
                )
            )
            .mappings()
            .all()
        )
        return [_principal_summary(dict(row)) for row in rows], total

    async def create_principal(
        self,
        *,
        principal_id: str,
        code: str,
        display_name: str,
        actor_user_id: str,
        now: datetime,
    ) -> ServicePrincipal:
        row = (
            (
                await self.connection.execute(
                    text(
                        """
                    INSERT INTO service_principal (
                        id, code, display_name, status, created_by_user_id, created_at, updated_at
                    )
                    VALUES (:id, :code, :display_name, 'ACTIVE', :actor_user_id, :now, :now)
                    RETURNING *
                    """
                    ),
                    {
                        "id": principal_id,
                        "code": code,
                        "display_name": display_name,
                        "actor_user_id": actor_user_id,
                        "now": now,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _principal(dict(row))

    async def read_principal(
        self, principal_id: str, *, for_update: bool = False
    ) -> ServicePrincipal | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await self.connection.execute(
                    text(f"SELECT * FROM service_principal WHERE id = :id{suffix}"),
                    {"id": principal_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _principal(dict(row)) if row is not None else None

    async def update_principal(
        self,
        *,
        principal_id: str,
        display_name: str,
        status: str,
        now: datetime,
    ) -> ServicePrincipal:
        row = (
            (
                await self.connection.execute(
                    text(
                        """
                    UPDATE service_principal
                    SET display_name = :display_name, status = :status, updated_at = :now
                    WHERE id = :id
                    RETURNING *
                    """
                    ),
                    {
                        "id": principal_id,
                        "display_name": display_name,
                        "status": status,
                        "now": now,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _principal(dict(row))

    async def create_token(
        self,
        *,
        principal_id: str,
        name: str,
        token_prefix: str,
        token_hash: str,
        scopes: tuple[str, ...],
        actor_user_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> ServiceTokenMetadata:
        row = (
            (
                await self.connection.execute(
                    text(
                        """
                    INSERT INTO service_token (
                        service_principal_id, name, token_prefix, token_hash, scope_json,
                        created_by_user_id, created_at, expires_at
                    )
                    VALUES (
                        :principal_id, :name, :token_prefix, :token_hash,
                        CAST(:scope_json AS jsonb), :actor_user_id, :now, :expires_at
                    )
                    RETURNING *
                    """
                    ),
                    {
                        "principal_id": principal_id,
                        "name": name,
                        "token_prefix": token_prefix,
                        "token_hash": token_hash,
                        "scope_json": json.dumps(list(scopes), separators=(",", ":")),
                        "actor_user_id": actor_user_id,
                        "now": now,
                        "expires_at": expires_at,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _token(dict(row))

    async def list_tokens(
        self, principal_id: str, *, include_revoked: bool
    ) -> list[ServiceTokenMetadata]:
        revoked_filter = "" if include_revoked else " AND revoked_at IS NULL"
        rows = (
            (
                await self.connection.execute(
                    text(
                        f"""
                    SELECT * FROM service_token
                    WHERE service_principal_id = :principal_id{revoked_filter}
                    ORDER BY created_at DESC, id DESC
                    """
                    ),
                    {"principal_id": principal_id},
                )
            )
            .mappings()
            .all()
        )
        return [_token(dict(row)) for row in rows]

    async def read_token(
        self,
        principal_id: str,
        token_id: int,
        *,
        for_update: bool,
    ) -> ServiceTokenMetadata | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await self.connection.execute(
                    text(
                        f"""
                    SELECT * FROM service_token
                    WHERE id = :token_id AND service_principal_id = :principal_id{suffix}
                    """
                    ),
                    {"token_id": token_id, "principal_id": principal_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _token(dict(row)) if row is not None else None

    async def revoke_token(self, token_id: int, *, now: datetime) -> None:
        await self.connection.execute(
            text(
                "UPDATE service_token SET revoked_at = COALESCE(revoked_at, :now) WHERE id = :id"
            ),
            {"id": token_id, "now": now},
        )
