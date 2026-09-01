from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import text

from app.api.skills import build_skill_search_response


SocialListKind = Literal["stars", "subscriptions"]


def _relationship_table(kind: SocialListKind) -> str:
    return "skill_star" if kind == "stars" else "skill_subscription"


async def list_my_social_skills(
    engine: Any,
    *,
    kind: SocialListKind,
    user_id: str,
    page: int,
    size: int,
) -> dict[str, object]:
    table_name = _relationship_table(kind)
    offset = page * size

    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name} rel WHERE rel.user_id = :user_id"),
                {"user_id": user_id},
            )
        ).scalar_one()

        rows = (
            await connection.execute(
                text(
                    f"""
                    WITH page_rel AS (
                        SELECT rel.skill_id, rel.created_at
                        FROM {table_name} rel
                        WHERE rel.user_id = :user_id
                        ORDER BY rel.created_at DESC, rel.skill_id DESC
                        LIMIT :limit OFFSET :offset
                    )
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.download_count,
                           s.star_count,
                           s.rating_avg,
                           s.rating_count,
                           n.slug AS namespace,
                           s.owner_id,
                           NULLIF(BTRIM(owner.display_name), '') AS owner_display_name,
                           s.updated_at,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           CASE WHEN pv.id IS NULL THEN 'NONE' ELSE 'PUBLISHED' END AS resolution_mode
                    FROM page_rel rel
                    JOIN skill s ON s.id = rel.skill_id
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN user_account owner ON owner.id = s.owner_id
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    ORDER BY rel.created_at DESC, rel.skill_id DESC
                    """
                ),
                {"user_id": user_id, "limit": size, "offset": offset},
            )
        ).mappings().all()

    return build_skill_search_response([dict(row) for row in rows], int(total), page, size)
