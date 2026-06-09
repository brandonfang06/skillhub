from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.promotion.query import PLATFORM_PROMOTION_ROLES, _java_instant, _promotion_response, _read_platform_roles


NAMESPACE_PROMOTION_ROLES = {"OWNER", "ADMIN"}


@dataclass(frozen=True)
class PromotionSubmitInput:
    source_skill_id: int
    source_version_id: int
    target_namespace_id: int
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class PromotionRejectInput:
    promotion_id: int
    reviewer_id: str
    comment: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


class PromotionWorkflowError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _detail_with_comment(comment: str | None) -> str | None:
    if comment is None or comment.strip() == "":
        return None
    return json.dumps({"comment": comment}, separators=(",", ":"))


async def _read_namespace_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT role
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    return str(row["role"]) if row is not None else None


async def _read_submit_context(connection: Any, request: PromotionSubmitInput) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT source_skill.id AS source_skill_id,
                       source_skill.namespace_id AS source_namespace_id,
                       source_skill.owner_id,
                       source_skill.slug AS skill_slug,
                       source_ns.slug AS source_namespace,
                       source_ns.status AS source_namespace_status,
                       source_version.id AS source_version_id,
                       source_version.skill_id AS version_skill_id,
                       source_version.status AS version_status,
                       source_version.version AS version_name,
                       target_ns.id AS target_namespace_id,
                       target_ns.slug AS target_namespace,
                       target_ns.type AS target_namespace_type,
                       submitter.display_name AS submitted_by_name
                FROM skill source_skill
                JOIN namespace source_ns ON source_ns.id = source_skill.namespace_id
                JOIN skill_version source_version ON source_version.id = :source_version_id
                JOIN namespace target_ns ON target_ns.id = :target_namespace_id
                LEFT JOIN user_account submitter ON submitter.id = :user_id
                WHERE source_skill.id = :source_skill_id
                """
            ),
            {
                "source_skill_id": request.source_skill_id,
                "source_version_id": request.source_version_id,
                "target_namespace_id": request.target_namespace_id,
                "user_id": request.user_id,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        raise PromotionWorkflowError("skill.not_found", status_code=404)
    return dict(row)


def _assert_submit_context(context: dict[str, Any], request: PromotionSubmitInput) -> None:
    if int(context["version_skill_id"]) != int(request.source_skill_id):
        raise PromotionWorkflowError("promotion.version_skill_mismatch")
    if str(context["version_status"]) != "PUBLISHED":
        raise PromotionWorkflowError("promotion.version_not_published")
    if str(context["source_namespace_status"]) == "FROZEN":
        raise PromotionWorkflowError("error.namespace.frozen")
    if str(context["source_namespace_status"]) == "ARCHIVED":
        raise PromotionWorkflowError("error.namespace.archived")
    if str(context["target_namespace_type"]) != "GLOBAL":
        raise PromotionWorkflowError("promotion.target_not_global")


async def _assert_can_submit(connection: Any, context: dict[str, Any], request: PromotionSubmitInput) -> None:
    platform_roles = await _read_platform_roles(connection, request.user_id)
    if str(context["owner_id"]) == request.user_id or platform_roles & PLATFORM_PROMOTION_ROLES:
        return
    namespace_role = await _read_namespace_role(connection, int(context["source_namespace_id"]), request.user_id)
    if namespace_role not in NAMESPACE_PROMOTION_ROLES:
        raise PromotionWorkflowError("promotion.no_permission", status_code=403)


async def _assert_no_duplicate_promotion(connection: Any, source_skill_id: int) -> None:
    duplicate = (
        await connection.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'APPROVED') AS approved_count
                FROM promotion_request
                WHERE source_skill_id = :source_skill_id
                """
            ),
            {"source_skill_id": source_skill_id},
        )
    ).mappings().one_or_none()
    if duplicate is None:
        return
    if int(duplicate["pending_count"]) > 0:
        raise PromotionWorkflowError("promotion.duplicate_pending")
    if int(duplicate["approved_count"]) > 0:
        raise PromotionWorkflowError("promotion.already_promoted")


async def _insert_audit_log(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail_json: str | None,
    created_at: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, :target_type, :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": detail_json,
            "created_at": created_at,
        },
    )


async def _read_promotion_response_row(connection: Any, promotion_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT pr.id,
                       pr.source_skill_id,
                       source_ns.slug AS source_namespace,
                       source_skill.slug AS skill_slug,
                       source_version.version AS version_name,
                       target_ns.slug AS target_namespace,
                       pr.target_skill_id,
                       pr.status,
                       pr.version,
                       pr.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       pr.reviewed_by,
                       reviewer.display_name AS reviewed_by_name,
                       pr.review_comment,
                       pr.submitted_at,
                       pr.reviewed_at
                FROM promotion_request pr
                JOIN skill source_skill ON source_skill.id = pr.source_skill_id
                JOIN skill_version source_version ON source_version.id = pr.source_version_id
                JOIN namespace source_ns ON source_ns.id = source_skill.namespace_id
                JOIN namespace target_ns ON target_ns.id = pr.target_namespace_id
                LEFT JOIN user_account submitter ON submitter.id = pr.submitted_by
                LEFT JOIN user_account reviewer ON reviewer.id = pr.reviewed_by
                WHERE pr.id = :promotion_id
                """
            ),
            {"promotion_id": promotion_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise PromotionWorkflowError("promotion.not_found", status_code=404)
    return dict(row)


async def _read_user_display_name(connection: Any, user_id: str) -> str | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT display_name
                FROM user_account
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return str(row["display_name"]) if row is not None and row.get("display_name") is not None else None


def _can_review(submitted_by: str, reviewer_id: str, platform_roles: set[str]) -> bool:
    return submitted_by != reviewer_id and bool(platform_roles & PLATFORM_PROMOTION_ROLES)


async def submit_promotion(engine: Any, request: PromotionSubmitInput) -> dict[str, Any]:
    submitted_at = _now(request.now)
    async with engine.begin() as connection:
        context = await _read_submit_context(connection, request)
        _assert_submit_context(context, request)
        await _assert_can_submit(connection, context, request)
        await _assert_no_duplicate_promotion(connection, request.source_skill_id)

        inserted = (
            await connection.execute(
                text(
                    """
                    INSERT INTO promotion_request (
                        source_skill_id, source_version_id, target_namespace_id,
                        status, version, submitted_by, submitted_at
                    )
                    VALUES (
                        :source_skill_id, :source_version_id, :target_namespace_id,
                        'PENDING', 1, :submitted_by, :submitted_at
                    )
                    RETURNING id, submitted_at
                    """
                ),
                {
                    "source_skill_id": request.source_skill_id,
                    "source_version_id": request.source_version_id,
                    "target_namespace_id": request.target_namespace_id,
                    "submitted_by": request.user_id,
                    "submitted_at": submitted_at,
                },
            )
        ).mappings().one_or_none()
        if inserted is None:
            raise PromotionWorkflowError("promotion.submit_failed")

        promotion_id = int(inserted["id"])
        await _insert_audit_log(
            connection,
            actor_user_id=request.user_id,
            action="PROMOTION_SUBMIT",
            target_type="PROMOTION_REQUEST",
            target_id=promotion_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps(
                {"sourceSkillId": request.source_skill_id, "sourceVersionId": request.source_version_id},
                separators=(",", ":"),
            ),
            created_at=submitted_at,
        )

        response_row = await _read_promotion_response_row(connection, promotion_id)
        response_row["submitted_by"] = request.user_id
        response_row["submitted_at"] = inserted["submitted_at"]

    return _promotion_response(response_row)


async def reject_promotion(engine: Any, request: PromotionRejectInput) -> dict[str, Any]:
    reviewed_at = _now(request.now)
    async with engine.begin() as connection:
        row = await _read_promotion_response_row(connection, request.promotion_id)
        if str(row["status"]) != "PENDING":
            raise PromotionWorkflowError("promotion.not_pending")
        platform_roles = await _read_platform_roles(connection, request.reviewer_id)
        if not _can_review(str(row["submitted_by"]), request.reviewer_id, platform_roles):
            raise PromotionWorkflowError("promotion.no_permission", status_code=403)

        updated = (
            await connection.execute(
                text(
                    """
                    UPDATE promotion_request
                    SET status = :status,
                        reviewed_by = :reviewed_by,
                        review_comment = :review_comment,
                        reviewed_at = :reviewed_at,
                        target_skill_id = NULL,
                        version = version + 1
                    WHERE id = :promotion_id
                      AND version = :expected_version
                      AND status = 'PENDING'
                    RETURNING 1
                    """
                ),
                {
                    "promotion_id": request.promotion_id,
                    "status": "REJECTED",
                    "reviewed_by": request.reviewer_id,
                    "review_comment": request.comment,
                    "reviewed_at": reviewed_at,
                    "expected_version": int(row["version"]),
                },
            )
        ).scalar_one()
        if int(updated) == 0:
            raise PromotionWorkflowError("promotion.concurrent_update", status_code=409)

        await _insert_audit_log(
            connection,
            actor_user_id=request.reviewer_id,
            action="PROMOTION_REJECT",
            target_type="PROMOTION_REQUEST",
            target_id=request.promotion_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=_detail_with_comment(request.comment),
            created_at=reviewed_at,
        )

        await connection.execute(
            text(
                """
                INSERT INTO user_notification (
                    user_id, category, entity_type, entity_id, title, body_json, status, created_at
                )
                VALUES (
                    :user_id, :category, :entity_type, :entity_id, :title, :body_json, 'UNREAD', :created_at
                )
                """
            ),
            {
                "user_id": str(row["submitted_by"]),
                "category": "PROMOTION",
                "entity_type": "PROMOTION_REQUEST",
                "entity_id": request.promotion_id,
                "title": "Promotion rejected",
                "body_json": json.dumps({"status": "REJECTED"}, separators=(",", ":")),
                "created_at": reviewed_at,
            },
        )

        row["status"] = "REJECTED"
        row["reviewed_by"] = request.reviewer_id
        row["reviewed_by_name"] = await _read_user_display_name(connection, request.reviewer_id)
        row["review_comment"] = request.comment
        row["reviewed_at"] = reviewed_at

    response = _promotion_response(row)
    response["reviewedAt"] = _java_instant(reviewed_at)
    return response
