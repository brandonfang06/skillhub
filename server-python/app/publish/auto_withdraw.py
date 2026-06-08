from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def auto_withdraw_pending_review_versions(
    connection: Any,
    *,
    skill_id: int,
) -> list[int]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM skill_version
                WHERE skill_id = :skill_id
                  AND status = 'PENDING_REVIEW'
                ORDER BY id ASC
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().all()
    version_ids = [int(row["id"]) for row in rows]
    if not version_ids:
        return []

    await connection.execute(
        text(
            """
            DELETE FROM review_task
            WHERE skill_version_id = ANY(:version_ids)
              AND status = 'PENDING'
            """
        ),
        {"version_ids": version_ids},
    )
    await connection.execute(
        text(
            """
            UPDATE skill_version
            SET status = 'UPLOADED'
            WHERE id = ANY(:version_ids)
            """
        ),
        {"version_ids": version_ids},
    )
    return version_ids
