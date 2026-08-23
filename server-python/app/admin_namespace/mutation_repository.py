from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.namespace.locking import (
    lock_namespace_for_update,
    lock_namespace_members_for_update,
)
from app.skills.read_responses import to_java_instant


class AdminNamespaceMutationError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


def _member_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "namespaceId": int(row["namespace_id"]),
        "userId": str(row["user_id"]),
        "displayName": row["display_name"],
        "email": row["email"],
        "role": str(row["role"]),
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
    }


async def lock_namespace(connection: Any, slug: str) -> dict[str, Any]:
    row = await lock_namespace_for_update(connection, slug)
    if row is None:
        raise AdminNamespaceMutationError("error.namespace.slug.notFound")
    return row


async def require_active_user(connection: Any, user_id: str) -> None:
    status = (
        await connection.execute(
            text("SELECT status FROM user_account WHERE id = :user_id FOR SHARE"),
            {"user_id": user_id},
        )
    ).scalar_one_or_none()
    if status is None:
        raise AdminNamespaceMutationError("error.namespace.member.user.notFound")
    if str(status) != "ACTIVE":
        raise AdminNamespaceMutationError("error.namespace.member.user.inactive")


async def read_member_role(
    connection: Any, namespace_id: int, user_id: str
) -> str | None:
    role = (
        await connection.execute(
            text(
                """
                SELECT role FROM namespace_member
                WHERE namespace_id = :namespace_id AND user_id = :user_id
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).scalar_one_or_none()
    return str(role) if role is not None else None


async def read_member(
    connection: Any, namespace_id: int, user_id: str
) -> dict[str, Any] | None:
    row = (
        (
            await connection.execute(
                text(
                    """
                SELECT nm.id, nm.namespace_id, nm.user_id, ua.display_name, ua.email,
                       nm.role, nm.created_at, nm.updated_at
                FROM namespace_member nm
                JOIN user_account ua ON ua.id = nm.user_id
                WHERE nm.namespace_id = :namespace_id AND nm.user_id = :user_id
                """
                ),
                {"namespace_id": namespace_id, "user_id": user_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return _member_response(dict(row)) if row is not None else None


async def insert_member(
    connection: Any, namespace_id: int, user_id: str, role: str
) -> None:
    try:
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :user_id, :role)
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id, "role": role},
        )
    except IntegrityError as exc:
        raise AdminNamespaceMutationError(
            "error.namespace.member.alreadyExists"
        ) from exc


async def update_member_role(
    connection: Any, namespace_id: int, user_id: str, role: str
) -> None:
    await connection.execute(
        text(
            """
            UPDATE namespace_member
            SET role = :role, updated_at = CURRENT_TIMESTAMP
            WHERE namespace_id = :namespace_id AND user_id = :user_id
            """
        ),
        {"namespace_id": namespace_id, "user_id": user_id, "role": role},
    )


async def delete_member(connection: Any, namespace_id: int, user_id: str) -> None:
    await connection.execute(
        text(
            """
            DELETE FROM namespace_member
            WHERE namespace_id = :namespace_id AND user_id = :user_id
            """
        ),
        {"namespace_id": namespace_id, "user_id": user_id},
    )


async def lock_members(connection: Any, namespace_id: int) -> list[dict[str, Any]]:
    return await lock_namespace_members_for_update(connection, namespace_id)


async def update_namespace_status(
    connection: Any, namespace_id: int, target_status: str
) -> None:
    await connection.execute(
        text(
            """
            UPDATE namespace SET status = :status, updated_at = CURRENT_TIMESTAMP
            WHERE id = :namespace_id
            """
        ),
        {"namespace_id": namespace_id, "status": target_status},
    )


async def insert_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    namespace_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail: dict[str, Any],
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            ) VALUES (
                :actor_user_id, :action, 'NAMESPACE', :target_id, :request_id,
                :client_ip, :user_agent, CAST(:detail_json AS JSONB), :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_id": namespace_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": json.dumps(
                detail, ensure_ascii=False, separators=(",", ":")
            ),
            "created_at": datetime.now(UTC),
        },
    )
