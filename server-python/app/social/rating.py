from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class SkillRatingInput:
    skill_id: int
    user_id: str
    score: int
    now: datetime | None = None


class SkillRatingError(ValueError):
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
        raise SkillRatingError("skill.not_found", status_code=404)


def _validate_score(score: int) -> None:
    if score < 1 or score > 5:
        raise SkillRatingError("error.rating.score.invalid", status_code=400)


async def _read_score(connection: Any, *, skill_id: int, user_id: str) -> int | None:
    value = (
        await connection.execute(
            text(
                """
                SELECT score
                FROM skill_rating
                WHERE skill_id = :skill_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "user_id": user_id},
        )
    ).scalar_one_or_none()
    return int(value) if value is not None else None


async def _refresh_rating_stats(connection: Any, skill_id: int) -> None:
    await connection.execute(
        text(
            """
            UPDATE skill
            SET rating_avg = COALESCE((
                    SELECT AVG(score)::numeric(3, 2)
                    FROM skill_rating
                    WHERE skill_id = :skill_id
                ), 0.00),
                rating_count = (
                    SELECT COUNT(*)
                    FROM skill_rating
                    WHERE skill_id = :skill_id
                )
            WHERE id = :skill_id
            """
        ),
        {"skill_id": skill_id},
    )


async def rate_skill(engine: Any, request: SkillRatingInput) -> None:
    async with engine.begin() as connection:
        await _ensure_skill_exists(connection, request.skill_id)
        _validate_score(request.score)
        existing_score = await _read_score(connection, skill_id=request.skill_id, user_id=request.user_id)
        current_time = _now(request.now)
        if existing_score is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_rating (skill_id, user_id, score, created_at, updated_at)
                    VALUES (:skill_id, :user_id, :score, :created_at, :updated_at)
                    """
                ),
                {
                    "skill_id": request.skill_id,
                    "user_id": request.user_id,
                    "score": request.score,
                    "created_at": current_time,
                    "updated_at": current_time,
                },
            )
        else:
            await connection.execute(
                text(
                    """
                    UPDATE skill_rating
                    SET score = :score,
                        updated_at = :updated_at
                    WHERE skill_id = :skill_id
                      AND user_id = :user_id
                    """
                ),
                {
                    "skill_id": request.skill_id,
                    "user_id": request.user_id,
                    "score": request.score,
                    "updated_at": current_time,
                },
            )
        await _refresh_rating_stats(connection, request.skill_id)


async def check_skill_rating(engine: Any, skill_id: int, user_id: str | None) -> dict[str, object]:
    if user_id is None or user_id.strip() == "":
        return {"score": 0, "rated": False}
    async with engine.connect() as connection:
        await _ensure_skill_exists(connection, skill_id)
        score = await _read_score(connection, skill_id=skill_id, user_id=user_id.strip())
    if score is None:
        return {"score": 0, "rated": False}
    return {"score": score, "rated": True}
