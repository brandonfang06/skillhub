from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def lock_namespace_for_update(
    connection: Any, slug: str
) -> dict[str, Any] | None:
    row = (
        (
            await connection.execute(
                text(
                    """
                SELECT n.id, n.slug, n.status, n.type
                FROM namespace n
                WHERE n.slug = :slug
                LIMIT 1
                FOR UPDATE
                """
                ),
                {"slug": slug},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def lock_namespace_members_for_update(
    connection: Any, namespace_id: int
) -> list[dict[str, Any]]:
    rows = (
        (
            await connection.execute(
                text(
                    """
                SELECT user_id, role
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                ORDER BY id
                FOR UPDATE
                """
                ),
                {"namespace_id": namespace_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
