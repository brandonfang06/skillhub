from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.api.skills import can_access_skill_row, read_namespace_role


@dataclass(frozen=True)
class ClawHubStarRequest:
    canonical_slug: str
    user_id: str
    now: datetime | None = None


class ClawHubStarError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def from_clawhub_canonical_slug(canonical_slug: str) -> tuple[str, str]:
    separator_index = canonical_slug.find("--")
    if separator_index > 0:
        return canonical_slug[:separator_index], canonical_slug[separator_index + 2 :]
    return "global", canonical_slug


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


async def _read_visible_skill(connection: Any, *, canonical_slug: str, user_id: str) -> dict[str, Any]:
    namespace_slug, skill_slug = from_clawhub_canonical_slug(canonical_slug)
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id,
                       s.owner_id,
                       s.namespace_id,
                       s.visibility,
                       s.latest_version_id
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE n.slug = :namespace_slug
                  AND s.slug = :skill_slug
                  AND s.status <> 'ARCHIVED'
                ORDER BY CASE WHEN s.latest_version_id IS NULL THEN 1 ELSE 0 END,
                         s.updated_at DESC,
                         s.id DESC
                LIMIT 1
                """
            ),
            {"namespace_slug": namespace_slug, "skill_slug": skill_slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ClawHubStarError("error.skill.notFound", status_code=404)

    skill = dict(row)
    namespace_role = await read_namespace_role(connection, int(skill["namespace_id"]), user_id)
    if not can_access_skill_row(skill, user_id, namespace_role):
        raise ClawHubStarError("error.skill.notFound", status_code=404)
    return skill


async def _is_starred(connection: Any, *, skill_id: int, user_id: str) -> bool:
    exists = (
        await connection.execute(
            text(
                """
                SELECT 1
                FROM skill_star
                WHERE skill_id = :skill_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "user_id": user_id},
        )
    ).scalar_one_or_none()
    return exists is not None


async def _refresh_star_count(connection: Any, skill_id: int) -> None:
    await connection.execute(
        text(
            """
            UPDATE skill
            SET star_count = (
                SELECT COUNT(*)
                FROM skill_star
                WHERE skill_id = :skill_id
            )
            WHERE id = :skill_id
            """
        ),
        {"skill_id": skill_id},
    )


async def clawhub_star_skill(
    engine: Any,
    canonical_slug: str,
    user_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, bool]:
    async with engine.begin() as connection:
        skill = await _read_visible_skill(connection, canonical_slug=canonical_slug, user_id=user_id)
        skill_id = int(skill["id"])
        already_starred = await _is_starred(connection, skill_id=skill_id, user_id=user_id)
        if not already_starred:
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_star (skill_id, user_id, created_at)
                    VALUES (:skill_id, :user_id, :created_at)
                    """
                ),
                {"skill_id": skill_id, "user_id": user_id, "created_at": _now(now)},
            )
            await _refresh_star_count(connection, skill_id)
    return {"ok": True, "starred": True, "alreadyStarred": already_starred}


async def clawhub_unstar_skill(engine: Any, canonical_slug: str, user_id: str) -> dict[str, bool]:
    async with engine.begin() as connection:
        skill = await _read_visible_skill(connection, canonical_slug=canonical_slug, user_id=user_id)
        skill_id = int(skill["id"])
        already_unstarred = not await _is_starred(connection, skill_id=skill_id, user_id=user_id)
        if not already_unstarred:
            await connection.execute(
                text(
                    """
                    DELETE FROM skill_star
                    WHERE skill_id = :skill_id
                      AND user_id = :user_id
                    """
                ),
                {"skill_id": skill_id, "user_id": user_id},
            )
            await _refresh_star_count(connection, skill_id)
    return {"ok": True, "unstarred": True, "alreadyUnstarred": already_unstarred}
