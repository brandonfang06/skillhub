from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.social.subscription_access import (
    SubscriptionAccessFacts,
    can_access_subscription_metadata,
)


@dataclass(frozen=True)
class SkillSubscriptionInput:
    skill_id: int
    user_id: str
    now: datetime | None = None


class SkillSubscriptionError(ValueError):
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
        raise SkillSubscriptionError("skill.not_found", status_code=404)


async def _is_subscribed(connection: Any, *, skill_id: int, user_id: str) -> bool:
    exists = (
        await connection.execute(
            text(
                """
                SELECT 1
                FROM skill_subscription
                WHERE skill_id = :skill_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "user_id": user_id},
        )
    ).scalar_one_or_none()
    return exists is not None


async def _read_subscription_access_facts(
    connection: Any,
    *,
    skill_id: int,
    user_id: str,
) -> SubscriptionAccessFacts | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       s.owner_id,
                       s.visibility,
                       s.hidden,
                       s.latest_version_id,
                       (
                           SELECT sv.id
                           FROM skill_version sv
                           WHERE sv.skill_id = s.id
                             AND sv.status = 'PUBLISHED'
                             AND sv.download_ready = TRUE
                             AND sv.yanked_at IS NULL
                           ORDER BY sv.published_at DESC NULLS LAST,
                                    sv.created_at DESC NULLS LAST,
                                    sv.id DESC
                           LIMIT 1
                       ) AS published_version_id,
                       n.status AS namespace_status,
                       account.status AS account_status,
                       member.role AS namespace_role
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                LEFT JOIN user_account account ON account.id = :user_id
                LEFT JOIN namespace_member member
                  ON member.namespace_id = s.namespace_id
                 AND member.user_id = :user_id
                WHERE s.id = :skill_id
                FOR UPDATE OF s
                """
            ),
            {"skill_id": skill_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    return SubscriptionAccessFacts.from_row(dict(row)) if row is not None else None


async def subscribe_skill(engine: Any, request: SkillSubscriptionInput) -> None:
    async with engine.begin() as connection:
        facts = await _read_subscription_access_facts(
            connection,
            skill_id=request.skill_id,
            user_id=request.user_id,
        )
        if facts is None:
            raise SkillSubscriptionError("skill.not_found", status_code=404)
        if not can_access_subscription_metadata(facts, user_id=request.user_id):
            raise SkillSubscriptionError(
                "error.skill.subscription.noPermission",
                status_code=403,
            )
        if await _is_subscribed(connection, skill_id=request.skill_id, user_id=request.user_id):
            return
        await connection.execute(
            text(
                """
                INSERT INTO skill_subscription (skill_id, user_id, created_at)
                VALUES (:skill_id, :user_id, :created_at)
                """
            ),
            {
                "skill_id": request.skill_id,
                "user_id": request.user_id,
                "created_at": _now(request.now),
            },
        )
        await connection.execute(
            text(
                """
                UPDATE skill
                SET subscription_count = subscription_count + 1
                WHERE id = :skill_id
                """
            ),
            {"skill_id": request.skill_id},
        )


async def unsubscribe_skill(engine: Any, request: SkillSubscriptionInput) -> None:
    async with engine.begin() as connection:
        await _ensure_skill_exists(connection, request.skill_id)
        if not await _is_subscribed(connection, skill_id=request.skill_id, user_id=request.user_id):
            return
        await connection.execute(
            text(
                """
                DELETE FROM skill_subscription
                WHERE skill_id = :skill_id
                  AND user_id = :user_id
                """
            ),
            {"skill_id": request.skill_id, "user_id": request.user_id},
        )
        await connection.execute(
            text(
                """
                UPDATE skill
                SET subscription_count = CASE
                    WHEN subscription_count > 0 THEN subscription_count - 1
                    ELSE 0
                END
                WHERE id = :skill_id
                """
            ),
            {"skill_id": request.skill_id},
        )


async def check_skill_subscription(engine: Any, skill_id: int, user_id: str | None) -> bool:
    if user_id is None or user_id.strip() == "":
        return False
    async with engine.connect() as connection:
        await _ensure_skill_exists(connection, skill_id)
        return await _is_subscribed(connection, skill_id=skill_id, user_id=user_id.strip())
