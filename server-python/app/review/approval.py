from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.db.unit_of_work import transaction_connection

from app.admin.search import upsert_skill_search_document
from sqlalchemy.exc import IntegrityError

from app.auth.policy import NAMESPACE_MANAGER_ROLES, namespace_role_allows
from app.notifications.publisher import NotificationFanout
from app.review.notifications import (
    publish_review_notifications,
    read_review_submission_recipients,
    write_review_decision_notification,
    write_review_submitted_notifications,
)


PLATFORM_REVIEW_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
NAMESPACE_REVIEW_ROLES = NAMESPACE_MANAGER_ROLES


@dataclass(frozen=True)
class ReviewApproveInput:
    review_task_id: int
    reviewer_id: str
    comment: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class ReviewRejectInput:
    review_task_id: int
    reviewer_id: str
    comment: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class ReviewWithdrawInput:
    review_task_id: int
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class ReviewSubmitInput:
    skill_version_id: int
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


class ReviewApprovalError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _detail_with_comment(comment: str | None) -> str | None:
    if comment is None or comment.strip() == "":
        return None
    return json.dumps({"comment": comment}, separators=(",", ":"))


async def _write_review_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail_json: str | None,
    created_at: datetime,
) -> None:
    await write_audit_log(
        connection,
        actor_user_id=actor_user_id,
        action=action,
        target_type="REVIEW_TASK",
        target_id=target_id,
        request_id=request_id,
        client_ip=client_ip,
        user_agent=user_agent,
        detail={},
        detail_json=detail_json,
        created_at=created_at,
    )


def _metadata_value(parsed_metadata_json: object, key: str) -> str | None:
    if parsed_metadata_json is None:
        return None
    raw = parsed_metadata_json
    if isinstance(raw, str):
        if raw.strip() == "":
            return None
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReviewApprovalError("error.skill.metadata.invalid") from exc
    if not isinstance(raw, dict):
        return None
    value = raw.get(key)
    return str(value) if value is not None else None


def _can_review(
    task_row: dict[str, Any],
    reviewer_id: str,
    namespace_role: str | None,
    platform_roles: set[str],
) -> bool:
    namespace_id = int(task_row["namespace_id"])
    namespace_type = str(task_row["namespace_type"])
    submitted_by = str(task_row["submitted_by"])
    if submitted_by == reviewer_id:
        return "SUPER_ADMIN" in platform_roles or (
            namespace_type != "GLOBAL" and namespace_role_allows(namespace_role, NAMESPACE_REVIEW_ROLES)
        )
    if platform_roles & PLATFORM_REVIEW_ROLES:
        return True
    if namespace_type == "GLOBAL":
        return False
    return namespace_role_allows(namespace_role, NAMESPACE_REVIEW_ROLES) and namespace_id > 0


def _can_submit(
    version_row: dict[str, Any],
    user_id: str,
    namespace_role: str | None,
    platform_roles: set[str],
) -> bool:
    if str(version_row["owner_id"]) == user_id:
        return True
    if platform_roles & PLATFORM_REVIEW_ROLES:
        return True
    return namespace_role_allows(namespace_role, NAMESPACE_REVIEW_ROLES)


def _review_response(task_row: dict[str, Any], *, status: str, reviewer_id: str, comment: str | None, reviewed_at: datetime) -> dict[str, Any]:
    return {
        "id": int(task_row["id"]),
        "skillVersionId": int(task_row["skill_version_id"]),
        "namespace": str(task_row["namespace_slug"]),
        "skillSlug": str(task_row["skill_slug"]),
        "version": str(task_row["version_name"]),
        "status": status,
        "submittedBy": str(task_row["submitted_by"]),
        "submittedByName": task_row.get("submitted_by_name"),
        "reviewedBy": reviewer_id,
        "reviewedByName": None,
        "reviewComment": comment,
        "submittedAt": task_row["submitted_at"],
        "reviewedAt": reviewed_at,
    }


def _review_submit_response(
    version_row: dict[str, Any],
    *,
    review_task_id: int,
    submitted_at: datetime,
    user_id: str,
) -> dict[str, Any]:
    return {
        "id": review_task_id,
        "skillVersionId": int(version_row["skill_version_id"]),
        "namespace": str(version_row["namespace_slug"]),
        "skillSlug": str(version_row["skill_slug"]),
        "version": str(version_row["version_name"]),
        "status": "PENDING",
        "submittedBy": user_id,
        "submittedByName": version_row.get("submitted_by_name"),
        "reviewedBy": None,
        "reviewedByName": None,
        "reviewComment": None,
        "submittedAt": submitted_at,
        "reviewedAt": None,
    }


async def _read_platform_roles(connection: Any, user_id: str) -> set[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.code
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                WHERE urb.user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return {str(row["code"]) for row in rows}


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


async def _read_review_task(connection: Any, review_task_id: int) -> dict[str, Any]:
    task_row = (
        await connection.execute(
            text(
                """
                SELECT rt.id,
                       rt.skill_version_id,
                       rt.namespace_id,
                       rt.status,
                       rt.version,
                       rt.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       rt.submitted_at,
                       n.slug AS namespace_slug,
                       n.type AS namespace_type,
                       n.status AS namespace_status,
                       s.id AS skill_id,
                       s.slug AS skill_slug,
                       s.owner_id,
                       sv.version AS version_name,
                       sv.status AS version_status,
                       sv.requested_visibility,
                       sv.parsed_metadata_json
                FROM review_task rt
                JOIN namespace n ON n.id = rt.namespace_id
                JOIN skill_version sv ON sv.id = rt.skill_version_id
                JOIN skill s ON s.id = sv.skill_id
                LEFT JOIN user_account submitter ON submitter.id = rt.submitted_by
                WHERE rt.id = :review_task_id
                """
            ),
            {"review_task_id": review_task_id},
        )
    ).mappings().one_or_none()
    if task_row is None:
        raise ReviewApprovalError("review_task.not_found", status_code=404)
    return dict(task_row)


def _assert_review_task_pending(task: dict[str, Any]) -> None:
    if str(task["status"]) != "PENDING":
        raise ReviewApprovalError("review.not_pending")


def _assert_namespace_active(task: dict[str, Any]) -> None:
    if str(task["namespace_status"]) == "FROZEN":
        raise ReviewApprovalError("error.namespace.frozen")
    if str(task["namespace_status"]) == "ARCHIVED":
        raise ReviewApprovalError("error.namespace.archived")


async def _assert_can_review(connection: Any, task: dict[str, Any], reviewer_id: str) -> None:
    platform_roles = await _read_platform_roles(connection, reviewer_id)
    namespace_role = await _read_namespace_role(connection, int(task["namespace_id"]), reviewer_id)
    if not _can_review(task, reviewer_id, namespace_role, platform_roles):
        raise ReviewApprovalError("review.no_permission", status_code=403)


async def _read_review_submit_context(connection: Any, skill_version_id: int, user_id: str) -> dict[str, Any]:
    version_row = (
        await connection.execute(
            text(
                """
                SELECT sv.id AS skill_version_id,
                       sv.status AS version_status,
                       sv.version AS version_name,
                       s.id AS skill_id,
                       s.namespace_id,
                       s.slug AS skill_slug,
                       s.owner_id,
                       n.slug AS namespace_slug,
                       n.type AS namespace_type,
                       n.status AS namespace_status,
                       submitter.display_name AS submitted_by_name
                FROM skill_version sv
                JOIN skill s ON s.id = sv.skill_id
                JOIN namespace n ON n.id = s.namespace_id
                LEFT JOIN user_account submitter ON submitter.id = :user_id
                WHERE sv.id = :skill_version_id
                """
            ),
            {"skill_version_id": skill_version_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    if version_row is None:
        raise ReviewApprovalError("skill_version.not_found", status_code=404)
    return dict(version_row)


async def _assert_can_submit(connection: Any, version_row: dict[str, Any], user_id: str) -> None:
    platform_roles = await _read_platform_roles(connection, user_id)
    if str(version_row["owner_id"]) == user_id or platform_roles & PLATFORM_REVIEW_ROLES:
        return
    namespace_role = await _read_namespace_role(connection, int(version_row["namespace_id"]), user_id)
    if not _can_submit(version_row, user_id, namespace_role, platform_roles):
        raise ReviewApprovalError("review.submit.no_permission", status_code=403)


async def submit_review_task(
    engine: Any,
    request: ReviewSubmitInput,
    *,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    submitted_at = _now(request.now)
    notification_rows: list[dict[str, Any]] = []
    async with transaction_connection(engine) as connection:
        version_row = await _read_review_submit_context(connection, request.skill_version_id, request.user_id)
        _assert_namespace_active(version_row)
        await _assert_can_submit(connection, version_row, request.user_id)

        if str(version_row["version_status"]) not in {"DRAFT", "UPLOADED"}:
            raise ReviewApprovalError("review.submit.not_draft")

        duplicate_count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM review_task
                    WHERE skill_version_id = :skill_version_id
                      AND status = 'PENDING'
                    """
                ),
                {"skill_version_id": request.skill_version_id},
            )
        ).scalar_one()
        if int(duplicate_count) > 0:
            raise ReviewApprovalError("review.submit.duplicate")

        updated = (
            await connection.execute(
                text(
                    """
                    UPDATE skill_version
                    SET status = :status
                    WHERE id = :skill_version_id
                      AND status IN ('DRAFT', 'UPLOADED')
                    RETURNING 1
                    """
                ),
                {"skill_version_id": request.skill_version_id, "status": "PENDING_REVIEW"},
            )
        ).scalar_one()
        if int(updated) == 0:
            raise ReviewApprovalError("review.concurrent_update", status_code=409)

        try:
            task_row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO review_task (
                            skill_version_id, namespace_id, status, version, submitted_by, submitted_at
                        )
                        VALUES (
                            :skill_version_id, :namespace_id, 'PENDING', 1, :submitted_by, :submitted_at
                        )
                        RETURNING id, submitted_at
                        """
                    ),
                    {
                        "skill_version_id": request.skill_version_id,
                        "namespace_id": int(version_row["namespace_id"]),
                        "submitted_by": request.user_id,
                        "submitted_at": submitted_at,
                    },
                )
            ).mappings().one_or_none()
        except IntegrityError as exc:
            raise ReviewApprovalError("review.submit.duplicate") from exc

        if task_row is None:
            raise ReviewApprovalError("review.submit.duplicate")
        review_task_id = int(task_row["id"])
        task_submitted_at = task_row["submitted_at"]

        await _write_review_audit(
            connection,
            actor_user_id=request.user_id,
            action="REVIEW_SUBMIT",
            target_id=review_task_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps({"skillVersionId": int(request.skill_version_id)}, separators=(",", ":")),
            created_at=submitted_at,
        )
        notification_rows = await write_review_submitted_notifications(
            connection,
            recipients=await read_review_submission_recipients(
                connection,
                namespace_id=int(version_row["namespace_id"]),
            ),
            review_task_id=review_task_id,
            skill_id=int(version_row["skill_id"]),
            version_id=int(request.skill_version_id),
            submitter_id=request.user_id,
            namespace=str(version_row["namespace_slug"]),
            slug=str(version_row["skill_slug"]),
            skill_name=_metadata_value(version_row.get("parsed_metadata_json"), "name"),
            version=str(version_row["version_name"]),
            created_at=submitted_at,
        )

    await publish_review_notifications(notification_fanout, notification_rows)
    return _review_submit_response(
        version_row,
        review_task_id=review_task_id,
        submitted_at=task_submitted_at,
        user_id=request.user_id,
    )


async def approve_review_task(
    engine: Any,
    request: ReviewApproveInput,
    *,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    reviewed_at = _now(request.now)
    notification_rows: list[dict[str, Any]] = []
    async with transaction_connection(engine) as connection:
        task = await _read_review_task(connection, request.review_task_id)
        _assert_review_task_pending(task)
        _assert_namespace_active(task)
        if str(task["version_status"]) == "SCANNING":
            raise ReviewApprovalError("review.approve.scan_in_progress")

        await _assert_can_review(connection, task, request.reviewer_id)

        conflict_count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM skill other
                    WHERE other.namespace_id = :namespace_id
                      AND other.slug = :slug
                      AND other.id <> :skill_id
                      AND EXISTS (
                          SELECT 1
                          FROM skill_version osv
                          WHERE osv.skill_id = other.id
                            AND osv.status = 'PUBLISHED'
                      )
                    """
                ),
                {
                    "namespace_id": int(task["namespace_id"]),
                    "slug": str(task["skill_slug"]),
                    "skill_id": int(task["skill_id"]),
                },
            )
        ).scalar_one()
        if int(conflict_count) > 0:
            raise ReviewApprovalError(f"error.skill.approve.nameConflict: {task['skill_slug']}")

        updated = (
            await connection.execute(
                text(
                    """
                    UPDATE review_task
                    SET status = :status,
                        reviewed_by = :reviewed_by,
                        review_comment = :review_comment,
                        reviewed_at = :reviewed_at,
                        version = version + 1
                    WHERE id = :review_task_id
                      AND version = :expected_version
                      AND status = 'PENDING'
                    RETURNING 1
                    """
                ),
                {
                    "review_task_id": request.review_task_id,
                    "status": "APPROVED",
                    "reviewed_by": request.reviewer_id,
                    "review_comment": request.comment,
                    "reviewed_at": reviewed_at,
                    "expected_version": int(task["version"]),
                },
            )
        ).scalar_one()
        if int(updated) == 0:
            raise ReviewApprovalError("review.concurrent_update", status_code=409)

        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status,
                    published_at = :published_at
                WHERE id = :skill_version_id
                """
            ),
            {
                "skill_version_id": int(task["skill_version_id"]),
                "status": "PUBLISHED",
                "published_at": reviewed_at,
            },
        )

        await connection.execute(
            text(
                """
                UPDATE skill
                SET latest_version_id = :latest_version_id,
                    visibility = :visibility,
                    display_name = COALESCE(:display_name, display_name),
                    summary = COALESCE(:summary, summary),
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "skill_id": int(task["skill_id"]),
                "latest_version_id": int(task["skill_version_id"]),
                "visibility": task["requested_visibility"],
                "display_name": _metadata_value(task.get("parsed_metadata_json"), "name"),
                "summary": _metadata_value(task.get("parsed_metadata_json"), "description"),
                "updated_by": request.reviewer_id,
                "updated_at": reviewed_at,
            },
        )

        await _write_review_audit(
            connection,
            actor_user_id=request.reviewer_id,
            action="REVIEW_APPROVE",
            target_id=request.review_task_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=_detail_with_comment(request.comment),
            created_at=reviewed_at,
        )
        await upsert_skill_search_document(connection, int(task["skill_id"]))
        notification_rows = await write_review_decision_notification(
            connection,
            recipient_id=str(task["submitted_by"]),
            approved=True,
            review_task_id=request.review_task_id,
            skill_id=int(task["skill_id"]),
            version_id=int(task["skill_version_id"]),
            reviewer_id=request.reviewer_id,
            namespace=str(task["namespace_slug"]),
            slug=str(task["skill_slug"]),
            skill_name=_metadata_value(task.get("parsed_metadata_json"), "name"),
            version=str(task["version_name"]),
            comment=request.comment,
            created_at=reviewed_at,
        )

    await publish_review_notifications(notification_fanout, notification_rows)
    return _review_response(task, status="APPROVED", reviewer_id=request.reviewer_id, comment=request.comment, reviewed_at=reviewed_at)


async def reject_review_task(
    engine: Any,
    request: ReviewRejectInput,
    *,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    reviewed_at = _now(request.now)
    notification_rows: list[dict[str, Any]] = []
    async with transaction_connection(engine) as connection:
        task = await _read_review_task(connection, request.review_task_id)
        _assert_review_task_pending(task)
        _assert_namespace_active(task)
        await _assert_can_review(connection, task, request.reviewer_id)

        updated = (
            await connection.execute(
                text(
                    """
                    UPDATE review_task
                    SET status = :status,
                        reviewed_by = :reviewed_by,
                        review_comment = :review_comment,
                        reviewed_at = :reviewed_at,
                        version = version + 1
                    WHERE id = :review_task_id
                      AND version = :expected_version
                      AND status = 'PENDING'
                    RETURNING 1
                    """
                ),
                {
                    "review_task_id": request.review_task_id,
                    "status": "REJECTED",
                    "reviewed_by": request.reviewer_id,
                    "review_comment": request.comment,
                    "reviewed_at": reviewed_at,
                    "expected_version": int(task["version"]),
                },
            )
        ).scalar_one()
        if int(updated) == 0:
            raise ReviewApprovalError("review.concurrent_update", status_code=409)

        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status
                WHERE id = :skill_version_id
                """
            ),
            {
                "skill_version_id": int(task["skill_version_id"]),
                "status": "REJECTED",
            },
        )

        await _write_review_audit(
            connection,
            actor_user_id=request.reviewer_id,
            action="REVIEW_REJECT",
            target_id=request.review_task_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=_detail_with_comment(request.comment),
            created_at=reviewed_at,
        )
        notification_rows = await write_review_decision_notification(
            connection,
            recipient_id=str(task["submitted_by"]),
            approved=False,
            review_task_id=request.review_task_id,
            skill_id=int(task["skill_id"]),
            version_id=int(task["skill_version_id"]),
            reviewer_id=request.reviewer_id,
            namespace=str(task["namespace_slug"]),
            slug=str(task["skill_slug"]),
            skill_name=_metadata_value(task.get("parsed_metadata_json"), "name"),
            version=str(task["version_name"]),
            comment=request.comment,
            created_at=reviewed_at,
        )

    await publish_review_notifications(notification_fanout, notification_rows)
    return _review_response(task, status="REJECTED", reviewer_id=request.reviewer_id, comment=request.comment, reviewed_at=reviewed_at)


async def withdraw_review_task(engine: Any, request: ReviewWithdrawInput) -> None:
    updated_at = _now(request.now)
    async with transaction_connection(engine) as connection:
        task = await _read_review_task(connection, request.review_task_id)
        if str(task["status"]) != "PENDING":
            raise ReviewApprovalError("review_task.not_found_for_version", status_code=404)
        if str(task["submitted_by"]) != request.user_id:
            raise ReviewApprovalError("review.withdraw.not_submitter", status_code=403)
        _assert_namespace_active(task)
        if str(task["version_status"]) != "PENDING_REVIEW":
            raise ReviewApprovalError("review.withdraw.not_pending")

        deleted = (
            await connection.execute(
                text(
                    """
                    DELETE FROM review_task
                    WHERE id = :review_task_id
                      AND status = 'PENDING'
                    RETURNING 1
                    """
                ),
                {"review_task_id": request.review_task_id},
            )
        ).scalar_one()
        if int(deleted) == 0:
            raise ReviewApprovalError("review.concurrent_update", status_code=409)

        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status
                WHERE id = :skill_version_id
                """
            ),
            {
                "skill_version_id": int(task["skill_version_id"]),
                "status": "UPLOADED",
            },
        )

        await connection.execute(
            text(
                """
                UPDATE skill
                SET updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "skill_id": int(task["skill_id"]),
                "updated_by": request.user_id,
                "updated_at": updated_at,
            },
        )

        await _write_review_audit(
            connection,
            actor_user_id=request.user_id,
            action="REVIEW_WITHDRAW",
            target_id=request.review_task_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps({"skillVersionId": int(task["skill_version_id"])}, separators=(",", ":")),
            created_at=updated_at,
        )
