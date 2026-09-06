from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log


class SkillReviewError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SkillReviewInput:
    skill_id: int
    user_id: str
    score: int
    review_text: str
    expected_lock_version: int
    now: datetime | None = None


@dataclass(frozen=True)
class SkillReviewModerationInput:
    review_id: int
    moderator_id: str
    action: str
    reason: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _validate(score: int, review_text: str) -> str:
    if score < 1 or score > 5:
        raise SkillReviewError("error.rating.score.invalid")
    normalized = review_text.strip()
    if not normalized:
        raise SkillReviewError("error.review.text.required")
    if len(normalized) > 2000:
        raise SkillReviewError("error.review.text.too_long")
    return normalized


async def _skill_access(connection: Any, *, skill_id: int, user_id: str | None) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id, s.owner_id, s.visibility, s.namespace_id,
                       member.role AS namespace_role,
                       EXISTS (
                           SELECT 1 FROM skill_version published
                           WHERE published.skill_id = s.id
                             AND published.status = 'PUBLISHED'
                             AND published.download_ready = TRUE
                       ) AS has_published_version
                FROM skill s
                LEFT JOIN namespace_member member
                  ON member.namespace_id = s.namespace_id
                 AND member.user_id = :user_id
                WHERE s.id = :skill_id
                """
            ),
            {"skill_id": skill_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillReviewError("skill.not_found", status_code=404)
    return dict(row)


def _can_read_skill(access: dict[str, Any], user_id: str | None, platform_roles: set[str]) -> bool:
    if {"SKILL_ADMIN", "SUPER_ADMIN"} & platform_roles:
        return True
    if user_id and str(access["owner_id"]) == user_id:
        return True
    role = str(access.get("namespace_role") or "")
    if not bool(access["has_published_version"]):
        return False
    if str(access["visibility"]) == "PUBLIC":
        return True
    if str(access["visibility"]) == "NAMESPACE_ONLY":
        return role in {"OWNER", "ADMIN", "MEMBER"}
    return role in {"OWNER", "ADMIN"}


def _review_response(row: dict[str, Any], viewer_id: str | None = None) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "reviewId": int(row["id"]),
        "displayName": str(row.get("display_name") or row["user_id"]),
        "avatarUrl": row.get("avatar_url"),
        "score": int(row["score"]),
        "reviewText": row.get("review_text"),
        "status": str(row["review_status"]),
        "moderationReason": row.get("moderation_reason"),
        "authoredByViewer": viewer_id == str(row["user_id"]),
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "lockVersion": int(row["lock_version"]),
    }


async def list_skill_reviews(
    engine: Any,
    *,
    skill_id: int,
    user_id: str | None,
    platform_roles: set[str],
    page: int,
    size: int,
) -> dict[str, Any]:
    page = max(page, 0)
    size = min(max(size, 1), 100)
    include_hidden = bool({"SKILL_ADMIN", "SUPER_ADMIN"} & platform_roles)
    async with engine.connect() as connection:
        access = await _skill_access(connection, skill_id=skill_id, user_id=user_id)
        if not _can_read_skill(access, user_id, platform_roles):
            raise SkillReviewError("skill.not_found", status_code=404)
        params = {"skill_id": skill_id, "include_hidden": include_hidden, "limit": size, "offset": page * size}
        total = int((await connection.execute(text("""
            SELECT COUNT(*) FROM skill_rating
            WHERE skill_id = :skill_id
              AND review_text IS NOT NULL AND BTRIM(review_text) <> ''
              AND (:include_hidden OR review_status = 'VISIBLE')
        """), params)).scalar_one())
        rows = (await connection.execute(text("""
            SELECT sr.*, ua.display_name, ua.avatar_url
            FROM skill_rating sr
            JOIN user_account ua ON ua.id = sr.user_id
            WHERE sr.skill_id = :skill_id
              AND sr.review_text IS NOT NULL AND BTRIM(sr.review_text) <> ''
              AND (:include_hidden OR sr.review_status = 'VISIBLE')
            ORDER BY sr.updated_at DESC, sr.id DESC
            LIMIT :limit OFFSET :offset
        """), params)).mappings().all()
    return {"items": [_review_response(dict(row), user_id) for row in rows], "total": total, "page": page, "size": size}


async def get_my_skill_review(engine: Any, *, skill_id: int, user_id: str) -> dict[str, Any]:
    async with engine.connect() as connection:
        await _skill_access(connection, skill_id=skill_id, user_id=user_id)
        row = (await connection.execute(text("""
            SELECT sr.*, ua.display_name, ua.avatar_url
            FROM skill_rating sr JOIN user_account ua ON ua.id = sr.user_id
            WHERE sr.skill_id = :skill_id AND sr.user_id = :user_id
        """), {"skill_id": skill_id, "user_id": user_id})).mappings().one_or_none()
    if row is None:
        return {"rated": False, "reviewed": False, "score": 0, "reviewText": None, "status": "VISIBLE", "lockVersion": 0}
    response = _review_response(dict(row), user_id)
    response.update({"rated": True, "reviewed": bool(str(row.get("review_text") or "").strip())})
    return response


async def upsert_skill_review(engine: Any, request: SkillReviewInput) -> dict[str, Any]:
    review_text = _validate(request.score, request.review_text)
    current_time = _now(request.now)
    async with engine.begin() as connection:
        access = await _skill_access(connection, skill_id=request.skill_id, user_id=request.user_id)
        if not _can_read_skill(access, request.user_id, set()) or not bool(access["has_published_version"]):
            raise SkillReviewError("error.review.skill.not_interactable", status_code=409)
        existing = (await connection.execute(text("""
            SELECT id, lock_version FROM skill_rating
            WHERE skill_id = :skill_id AND user_id = :user_id FOR UPDATE
        """), {"skill_id": request.skill_id, "user_id": request.user_id})).mappings().one_or_none()
        if existing is None:
            if request.expected_lock_version != 0:
                raise SkillReviewError("error.review.concurrent_update", status_code=409)
            row = (await connection.execute(text("""
                INSERT INTO skill_rating (
                    skill_id, user_id, score, review_text, review_status,
                    lock_version, created_at, updated_at
                ) VALUES (
                    :skill_id, :user_id, :score, :review_text, 'VISIBLE',
                    0, :now, :now
                ) RETURNING *
            """), {"skill_id": request.skill_id, "user_id": request.user_id, "score": request.score, "review_text": review_text, "now": current_time})).mappings().one()
        else:
            if int(existing["lock_version"]) != request.expected_lock_version:
                raise SkillReviewError("error.review.concurrent_update", status_code=409)
            row = (await connection.execute(text("""
                UPDATE skill_rating
                SET score = :score, review_text = :review_text,
                    updated_at = :now, lock_version = lock_version + 1
                WHERE id = :id AND lock_version = :expected_lock_version
                RETURNING *
            """), {"id": int(existing["id"]), "score": request.score, "review_text": review_text, "now": current_time, "expected_lock_version": request.expected_lock_version})).mappings().one_or_none()
            if row is None:
                raise SkillReviewError("error.review.concurrent_update", status_code=409)
        await connection.execute(text("""
            UPDATE skill SET rating_avg = COALESCE((SELECT AVG(score)::numeric(3,2) FROM skill_rating WHERE skill_id = :skill_id), 0.00),
                rating_count = (SELECT COUNT(*) FROM skill_rating WHERE skill_id = :skill_id)
            WHERE id = :skill_id
        """), {"skill_id": request.skill_id})
        full = (await connection.execute(text("SELECT sr.*, ua.display_name, ua.avatar_url FROM skill_rating sr JOIN user_account ua ON ua.id = sr.user_id WHERE sr.id = :id"), {"id": int(row["id"])})).mappings().one()
    response = _review_response(dict(full), request.user_id)
    response.update({"rated": True, "reviewed": True})
    return response


async def clear_skill_review(engine: Any, *, skill_id: int, user_id: str, expected_lock_version: int, now: datetime | None = None) -> dict[str, Any]:
    async with engine.begin() as connection:
        await _skill_access(connection, skill_id=skill_id, user_id=user_id)
        row = (await connection.execute(text("""
            UPDATE skill_rating
            SET review_text = NULL, review_status = 'VISIBLE', moderated_by = NULL,
                moderated_at = NULL, moderation_reason = NULL,
                updated_at = :now, lock_version = lock_version + 1
            WHERE skill_id = :skill_id AND user_id = :user_id
              AND lock_version = :expected_lock_version
            RETURNING *
        """), {"skill_id": skill_id, "user_id": user_id, "expected_lock_version": expected_lock_version, "now": _now(now)})).mappings().one_or_none()
        if row is None:
            raise SkillReviewError("error.review.concurrent_update", status_code=409)
    response = _review_response(dict(row), user_id)
    response.update({"rated": True, "reviewed": False})
    return response


async def moderate_skill_review(engine: Any, request: SkillReviewModerationInput) -> dict[str, Any]:
    action = request.action.upper()
    if action not in {"HIDE", "RESTORE"}:
        raise SkillReviewError("error.review.moderation.action")
    reason = request.reason.strip() if request.reason else None
    if reason and len(reason) > 500:
        raise SkillReviewError("error.review.moderation.reason_too_long")
    current_time = _now(request.now)
    async with engine.begin() as connection:
        row = (await connection.execute(text("""
            UPDATE skill_rating
            SET review_status = :status, moderated_by = :moderator_id,
                moderated_at = :now, moderation_reason = :reason,
                lock_version = lock_version + 1, updated_at = :now
            WHERE id = :review_id
              AND review_text IS NOT NULL AND BTRIM(review_text) <> ''
            RETURNING *
        """), {"status": "HIDDEN" if action == "HIDE" else "VISIBLE", "moderator_id": request.moderator_id, "now": current_time, "reason": reason if action == "HIDE" else None, "review_id": request.review_id})).mappings().one_or_none()
        if row is None:
            raise SkillReviewError("error.review.not_found", status_code=404)
        await write_audit_log(
            connection,
            actor_user_id=request.moderator_id,
            action=f"{action}_SKILL_REVIEW",
            target_type="SKILL_REVIEW",
            target_id=request.review_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail={"skillId": int(row["skill_id"]), "reason": reason if action == "HIDE" else None},
            created_at=current_time,
        )
        full = (await connection.execute(text("SELECT sr.*, ua.display_name, ua.avatar_url FROM skill_rating sr JOIN user_account ua ON ua.id = sr.user_id WHERE sr.id = :id"), {"id": request.review_id})).mappings().one()
    return _review_response(dict(full), None)
