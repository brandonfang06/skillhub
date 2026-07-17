from __future__ import annotations

from typing import Any

from sqlalchemy import text


ZERO_DEPENDENCY_COUNTS = {"skillCount": 0, "reviewTaskCount": 0, "promotionRequestCount": 0}


async def read_namespace_dependency_counts_by_ids(
    connection: Any,
    namespace_ids: list[int],
) -> dict[int, dict[str, int]]:
    if not namespace_ids:
        return {}
    rows = (
        await connection.execute(
            text(
                """
                SELECT n.id AS namespace_id,
                    (SELECT COUNT(*) FROM skill WHERE namespace_id = n.id) AS skill_count,
                    (SELECT COUNT(*) FROM review_task WHERE namespace_id = n.id) AS review_task_count,
                    (
                        SELECT COUNT(*)
                        FROM promotion_request
                        WHERE target_namespace_id = n.id
                    ) AS promotion_request_count
                FROM namespace n
                WHERE n.id = ANY(CAST(:namespace_ids AS bigint[]))
                """
            ),
            {"namespace_ids": namespace_ids},
        )
    ).mappings().all()
    return {
        int(row["namespace_id"]): {
            "skillCount": int(row["skill_count"]),
            "reviewTaskCount": int(row["review_task_count"]),
            "promotionRequestCount": int(row["promotion_request_count"]),
        }
        for row in rows
    }


async def read_namespace_dependency_counts(connection: Any, namespace_id: int) -> dict[str, int]:
    counts_by_id = await read_namespace_dependency_counts_by_ids(connection, [namespace_id])
    return counts_by_id.get(namespace_id, ZERO_DEPENDENCY_COUNTS.copy())


def has_namespace_dependencies(counts: dict[str, int]) -> bool:
    return any(int(value) > 0 for value in counts.values())


__all__ = [
    "has_namespace_dependencies",
    "read_namespace_dependency_counts",
    "read_namespace_dependency_counts_by_ids",
]
