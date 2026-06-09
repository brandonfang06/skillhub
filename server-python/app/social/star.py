from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class SkillStarInput:
    skill_id: int
    user_id: str
    now: datetime | None = None


class SkillStarError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


async def _ensure_skill_exists(connection: Any, skill_id: int) -> None:
    exists = (
        await connection.execute(
            text(
                """
                SELECT 1
                FROM skill
                WHERE id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise SkillStarError("skill.not_found", status_code=404)


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


async def star_skill(engine: Any, request: SkillStarInput) -> None:
    async with engine.begin() as connection:
        await _ensure_skill_exists(connection, request.skill_id)
        if await _is_starred(connection, skill_id=request.skill_id, user_id=request.user_id):
            return
        await connection.execute(
            text(
                """
                INSERT INTO skill_star (skill_id, user_id, created_at)
                VALUES (:skill_id, :user_id, :created_at)
                """
            ),
            {
                "skill_id": request.skill_id,
                "user_id": request.user_id,
                "created_at": _now(request.now),
            },
        )
        await _refresh_star_count(connection, request.skill_id)


async def unstar_skill(engine: Any, request: SkillStarInput) -> None:
    async with engine.begin() as connection:
        await _ensure_skill_exists(connection, request.skill_id)
        if not await _is_starred(connection, skill_id=request.skill_id, user_id=request.user_id):
            return
        await connection.execute(
            text(
                """
                DELETE FROM skill_star
                WHERE skill_id = :skill_id
                  AND user_id = :user_id
                """
            ),
            {"skill_id": request.skill_id, "user_id": request.user_id},
        )
        await _refresh_star_count(connection, request.skill_id)


async def check_skill_star(engine: Any, skill_id: int, user_id: str | None) -> bool:
    if user_id is None or user_id.strip() == "":
        return False
    async with engine.connect() as connection:
        await _ensure_skill_exists(connection, skill_id)
        return await _is_starred(connection, skill_id=skill_id, user_id=user_id.strip())
