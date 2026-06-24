from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant
from app.notifications.publisher import NotificationFanout, publish_notification_rows


SKILL_REPORT_READ_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
PROFILE_REVIEW_READ_ROLES = {"USER_ADMIN", "SUPER_ADMIN"}
SKILL_REPORT_STATUSES = {"PENDING", "RESOLVED", "DISMISSED"}
PROFILE_REVIEW_STATUSES = {"PENDING", "MACHINE_REJECTED", "APPROVED", "REJECTED", "CANCELLED"}
REPORT_RESOLUTION_DISPOSITIONS = {"RESOLVE_ONLY", "RESOLVE_AND_HIDE", "RESOLVE_AND_ARCHIVE"}


class AdminReviewReportError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_skill_report_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(SKILL_REPORT_READ_ROLES):
        raise AdminReviewReportError("error.admin.skillReport.readDenied", status_code=403)


def require_profile_review_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(PROFILE_REVIEW_READ_ROLES):
        raise AdminReviewReportError("error.profileReview.readDenied", status_code=403)


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _db_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _normalize_comment(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _raw_reason_detail(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return json.dumps({"reason": value}, separators=(",", ":"))


def _normalize_status(status: str | None, allowed: set[str], default: str, error_key: str) -> str:
    if status is None or status.strip() == "":
        return default
    normalized = status.strip().upper()
    if normalized not in allowed:
        raise AdminReviewReportError(error_key, status_code=400)
    return normalized


def _normalize_disposition(disposition: str | None) -> str:
    normalized = _normalize_status(
        disposition,
        REPORT_RESOLUTION_DISPOSITIONS,
        "RESOLVE_ONLY",
        "error.skill.report.disposition.invalid",
    )
    return normalized


def _page_number(page: int) -> int:
    return max(0, int(page))


def _page_size(size: int) -> int:
    return max(1, int(size))


def _json_map(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _skill_report_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "skillId": int(row["skill_id"]),
        "namespace": row.get("namespace"),
        "skillSlug": row.get("skill_slug"),
        "skillDisplayName": row.get("skill_display_name"),
        "reporterId": row.get("reporter_id"),
        "reason": row.get("reason"),
        "details": row.get("details"),
        "status": row.get("status"),
        "handledBy": row.get("handled_by"),
        "handleComment": row.get("handle_comment"),
        "createdAt": to_java_instant(row.get("created_at")),
        "handledAt": to_java_instant(row.get("handled_at")) if row.get("handled_at") is not None else None,
    }


def _profile_review_item(row: dict[str, Any]) -> dict[str, Any]:
    changes = _json_map(row.get("changes"))
    old_values = _json_map(row.get("old_values"))
    submitter_name = row.get("submitter_name")
    return {
        "id": int(row["id"]),
        "userId": row.get("user_id"),
        "username": submitter_name if submitter_name is not None else row.get("user_id"),
        "currentDisplayName": old_values.get("displayName", submitter_name),
        "requestedDisplayName": changes.get("displayName"),
        "status": row.get("status"),
        "machineResult": row.get("machine_result"),
        "reviewerId": row.get("reviewer_id"),
        "reviewerName": row.get("reviewer_name"),
        "reviewComment": row.get("review_comment"),
        "createdAt": to_java_instant(row.get("created_at")),
        "reviewedAt": to_java_instant(row.get("reviewed_at")) if row.get("reviewed_at") is not None else None,
    }


async def _read_skill_report(connection: Any, report_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id,
                       skill_id,
                       reporter_id,
                       status
                FROM skill_report
                WHERE id = :report_id
                LIMIT 1
                """
            ),
            {"report_id": report_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminReviewReportError("error.skill.report.notFound", status_code=404)
    return dict(row)


async def _read_profile_review(connection: Any, request_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id,
                       user_id,
                       changes,
                       status
                FROM profile_change_request
                WHERE id = :request_id
                LIMIT 1
                """
            ),
            {"request_id": request_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminReviewReportError("error.profileReview.notFound", status_code=404)
    return dict(row)


async def _read_user(connection: Any, user_id: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id,
                       display_name
                FROM user_account
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminReviewReportError("error.user.notFound", status_code=404)
    return dict(row)


async def _write_audit(
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


async def _write_report_notification(
    connection: Any,
    *,
    user_id: str,
    entity_id: int,
    title: str,
    body_json: str,
    created_at: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO user_notification (
                user_id, category, entity_type, entity_id, title, body_json, status, created_at
            )
            VALUES (
                :user_id, :category, :entity_type, :entity_id, :title, :body_json, :status, :created_at
            )
            """
        ),
        {
            "user_id": user_id,
            "category": "REPORT",
            "entity_type": "SKILL_REPORT",
            "entity_id": entity_id,
            "title": title,
            "body_json": body_json,
            "status": "UNREAD",
            "created_at": created_at,
        },
    )


async def _read_skill_notification_context(connection: Any, skill_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.slug AS slug,
                       s.display_name AS display_name,
                       n.slug AS namespace
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE s.id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminReviewReportError("error.skill.notFound", status_code=404)
    return dict(row)


async def _in_app_report_notifications_enabled(connection: Any, user_id: str) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT COALESCE(np.enabled, TRUE) AS enabled
                FROM (SELECT :user_id AS user_id) target
                LEFT JOIN notification_preference np
                  ON np.user_id = target.user_id
                 AND np.category = 'REPORT'
                 AND np.channel = 'IN_APP'
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return True if row is None else bool(row["enabled"])


def _skill_display_name(skill: dict[str, Any]) -> str:
    display_name = skill.get("display_name")
    if display_name is not None and str(display_name).strip() != "":
        return str(display_name)
    return str(skill["slug"])


async def _write_report_resolved_notification(
    connection: Any,
    *,
    reporter_id: str,
    report_id: int,
    skill_id: int,
    handler_id: str,
    action: str,
    created_at: datetime,
) -> list[dict[str, Any]]:
    if not await _in_app_report_notifications_enabled(connection, reporter_id):
        return []
    skill = await _read_skill_notification_context(connection, skill_id)
    display_name = _skill_display_name(skill)
    body_json = json.dumps(
        {
            "skillId": int(skill["skill_id"]),
            "skillName": display_name,
            "slug": str(skill["slug"]),
            "namespace": str(skill["namespace"]),
            "reportId": report_id,
            "handlerId": handler_id,
            "action": action,
        },
        separators=(",", ":"),
    )
    rows = (
        await connection.execute(
            text(
                """
                INSERT INTO notification (
                    recipient_id, category, event_type, title, body_json,
                    entity_type, entity_id, status, created_at
                )
                VALUES (
                    :recipient_id, :category, :event_type, :title, :body_json,
                    :entity_type, :entity_id, :status, :created_at
                )
                RETURNING id, recipient_id, category, event_type, title, body_json,
                          entity_type, entity_id, created_at
                """
            ),
            {
                "recipient_id": reporter_id,
                "category": "REPORT",
                "event_type": "REPORT_RESOLVED",
                "title": f"Report resolved: {display_name}",
                "body_json": body_json,
                "entity_type": "SKILL",
                "entity_id": skill_id,
                "status": "UNREAD",
                "created_at": created_at,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _apply_report_disposition(
    connection: Any,
    *,
    skill_id: int,
    disposition: str,
    actor_user_id: str,
    reason: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    timestamp: datetime,
) -> None:
    if disposition == "RESOLVE_AND_HIDE":
        await connection.execute(
            text(
                """
                UPDATE skill
                SET hidden = TRUE,
                    hidden_by = :actor_user_id,
                    hidden_at = :timestamp,
                    updated_by = :actor_user_id,
                    updated_at = :timestamp
                WHERE id = :skill_id
                """
            ),
            {"skill_id": skill_id, "actor_user_id": actor_user_id, "timestamp": timestamp},
        )
        await _write_audit(
            connection,
            actor_user_id=actor_user_id,
            action="HIDE_SKILL",
            target_type="SKILL",
            target_id=skill_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=_raw_reason_detail(reason),
            created_at=timestamp,
        )
    elif disposition == "RESOLVE_AND_ARCHIVE":
        await connection.execute(
            text(
                """
                UPDATE skill
                SET status = :status,
                    updated_by = :actor_user_id,
                    updated_at = :timestamp
                WHERE id = :skill_id
                """
            ),
            {"skill_id": skill_id, "status": "ARCHIVED", "actor_user_id": actor_user_id, "timestamp": timestamp},
        )
        await _write_audit(
            connection,
            actor_user_id=actor_user_id,
            action="ARCHIVE_SKILL",
            target_type="SKILL",
            target_id=skill_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=_raw_reason_detail(reason),
            created_at=timestamp,
        )


async def resolve_admin_skill_report(
    engine: Any,
    *,
    report_id: int,
    actor_user_id: str,
    platform_roles: list[str],
    disposition: str | None,
    comment: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    require_skill_report_reader(platform_roles)
    normalized_disposition = _normalize_disposition(disposition)
    roles = {str(role) for role in platform_roles}
    if normalized_disposition == "RESOLVE_AND_HIDE" and "SUPER_ADMIN" not in roles:
        raise AdminReviewReportError("error.skill.lifecycle.noPermission", status_code=403)

    timestamp = _now(now)
    normalized_comment = _normalize_comment(comment)
    notification_rows: list[dict[str, Any]] = []
    async with engine.begin() as connection:
        report = await _read_skill_report(connection, report_id)
        if str(report["status"]) != "PENDING":
            raise AdminReviewReportError("error.skill.report.alreadyHandled", status_code=400)

        await _apply_report_disposition(
            connection,
            skill_id=int(report["skill_id"]),
            disposition=normalized_disposition,
            actor_user_id=actor_user_id,
            reason=comment,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            timestamp=timestamp,
        )
        await connection.execute(
            text(
                """
                UPDATE skill_report
                SET status = :status,
                    handled_by = :handled_by,
                    handle_comment = :handle_comment,
                    handled_at = :handled_at
                WHERE id = :report_id
                """
            ),
            {
                "status": "RESOLVED",
                "handled_by": actor_user_id,
                "handle_comment": normalized_comment,
                "handled_at": timestamp,
                "report_id": report_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=actor_user_id,
            action="RESOLVE_SKILL_REPORT",
            target_type="SKILL_REPORT",
            target_id=report_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=None,
            created_at=timestamp,
        )
        await _write_report_notification(
            connection,
            user_id=str(report["reporter_id"]),
            entity_id=report_id,
            title="Report handled",
            body_json='{"status":"RESOLVED"}',
            created_at=timestamp,
        )
        notification_rows = await _write_report_resolved_notification(
            connection,
            reporter_id=str(report["reporter_id"]),
            report_id=report_id,
            skill_id=int(report["skill_id"]),
            handler_id=actor_user_id,
            action="resolved",
            created_at=timestamp,
        )
    await publish_notification_rows(notification_fanout, notification_rows)
    return {"id": report_id, "status": "RESOLVED"}


async def dismiss_admin_skill_report(
    engine: Any,
    *,
    report_id: int,
    actor_user_id: str,
    platform_roles: list[str],
    comment: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    require_skill_report_reader(platform_roles)
    timestamp = _now(now)
    normalized_comment = _normalize_comment(comment)
    notification_rows: list[dict[str, Any]] = []
    async with engine.begin() as connection:
        report = await _read_skill_report(connection, report_id)
        if str(report["status"]) != "PENDING":
            raise AdminReviewReportError("error.skill.report.alreadyHandled", status_code=400)

        await connection.execute(
            text(
                """
                UPDATE skill_report
                SET status = :status,
                    handled_by = :handled_by,
                    handle_comment = :handle_comment,
                    handled_at = :handled_at
                WHERE id = :report_id
                """
            ),
            {
                "status": "DISMISSED",
                "handled_by": actor_user_id,
                "handle_comment": normalized_comment,
                "handled_at": timestamp,
                "report_id": report_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=actor_user_id,
            action="DISMISS_SKILL_REPORT",
            target_type="SKILL_REPORT",
            target_id=report_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=None,
            created_at=timestamp,
        )
        await _write_report_notification(
            connection,
            user_id=str(report["reporter_id"]),
            entity_id=report_id,
            title="Report dismissed",
            body_json='{"status":"DISMISSED"}',
            created_at=timestamp,
        )
        notification_rows = await _write_report_resolved_notification(
            connection,
            reporter_id=str(report["reporter_id"]),
            report_id=report_id,
            skill_id=int(report["skill_id"]),
            handler_id=actor_user_id,
            action="dismissed",
            created_at=timestamp,
        )
    await publish_notification_rows(notification_fanout, notification_rows)
    return {"id": report_id, "status": "DISMISSED"}


async def approve_admin_profile_review(
    engine: Any,
    *,
    request_id: int,
    reviewer_id: str,
    platform_roles: list[str],
    http_request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    require_profile_review_reader(platform_roles)
    timestamp = _db_timestamp(_now(now))
    async with engine.begin() as connection:
        review = await _read_profile_review(connection, request_id)
        if str(review["status"]) != "PENDING":
            raise AdminReviewReportError("error.profileReview.notPending", status_code=400)

        user_id = str(review["user_id"])
        await _read_user(connection, user_id)
        changes = _json_map(review.get("changes"))
        if "displayName" in changes:
            await connection.execute(
                text(
                    """
                    UPDATE user_account
                    SET display_name = :display_name,
                        updated_at = :updated_at
                    WHERE id = :user_id
                    """
                ),
                {"display_name": changes.get("displayName"), "updated_at": timestamp, "user_id": user_id},
            )

        await connection.execute(
            text(
                """
                UPDATE profile_change_request
                SET status = :status,
                    reviewer_id = :reviewer_id,
                    review_comment = :review_comment,
                    reviewed_at = :reviewed_at
                WHERE id = :request_id
                """
            ),
            {
                "status": "APPROVED",
                "reviewer_id": reviewer_id,
                "review_comment": None,
                "reviewed_at": timestamp,
                "request_id": request_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=reviewer_id,
            action="PROFILE_REVIEW_APPROVE",
            target_type="PROFILE_CHANGE_REQUEST",
            target_id=request_id,
            request_id=http_request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=None,
            created_at=timestamp,
        )
    return {"id": request_id, "status": "APPROVED"}


async def reject_admin_profile_review(
    engine: Any,
    *,
    request_id: int,
    reviewer_id: str,
    platform_roles: list[str],
    comment: str,
    http_request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    require_profile_review_reader(platform_roles)
    timestamp = _db_timestamp(_now(now))
    async with engine.begin() as connection:
        review = await _read_profile_review(connection, request_id)
        if str(review["status"]) != "PENDING":
            raise AdminReviewReportError("error.profileReview.notPending", status_code=400)

        await connection.execute(
            text(
                """
                UPDATE profile_change_request
                SET status = :status,
                    reviewer_id = :reviewer_id,
                    review_comment = :review_comment,
                    reviewed_at = :reviewed_at
                WHERE id = :request_id
                """
            ),
            {
                "status": "REJECTED",
                "reviewer_id": reviewer_id,
                "review_comment": comment,
                "reviewed_at": timestamp,
                "request_id": request_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=reviewer_id,
            action="PROFILE_REVIEW_REJECT",
            target_type="PROFILE_CHANGE_REQUEST",
            target_id=request_id,
            request_id=http_request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            detail_json=json.dumps({"comment": comment}, separators=(",", ":")),
            created_at=timestamp,
        )
    return {"id": request_id, "status": "REJECTED"}


async def list_admin_skill_reports(
    engine: Any,
    *,
    status: str | None,
    page: int,
    size: int,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_skill_report_reader(platform_roles)
    normalized_status = _normalize_status(status, SKILL_REPORT_STATUSES, "PENDING", "error.skill.report.status.invalid")
    normalized_page = _page_number(page)
    normalized_size = _page_size(size)
    params = {
        "status": normalized_status,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
    }
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM skill_report sr WHERE sr.status = :status"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT sr.id,
                           sr.skill_id,
                           n.slug AS namespace,
                           s.slug AS skill_slug,
                           s.display_name AS skill_display_name,
                           sr.reporter_id,
                           sr.reason,
                           sr.details,
                           sr.status,
                           sr.handled_by,
                           sr.handle_comment,
                           sr.created_at,
                           sr.handled_at
                    FROM skill_report sr
                    LEFT JOIN skill s ON s.id = sr.skill_id
                    LEFT JOIN namespace n ON n.id = s.namespace_id
                    WHERE sr.status = :status
                    ORDER BY sr.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_skill_report_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


async def list_admin_profile_reviews(
    engine: Any,
    *,
    status: str | None,
    page: int,
    size: int,
    sort_direction: str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_profile_review_reader(platform_roles)
    normalized_status = _normalize_status(status, PROFILE_REVIEW_STATUSES, "PENDING", "error.profileReview.status.invalid")
    normalized_page = _page_number(page)
    normalized_size = _page_size(size)
    sort_desc = str(sort_direction or "DESC").strip().upper() != "ASC"
    sort_column = "created_at" if normalized_status == "PENDING" else "reviewed_at"
    sort_order = "DESC" if sort_desc else "ASC"
    params = {
        "status": normalized_status,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
        "sort_desc": sort_desc,
    }
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM profile_change_request pcr WHERE pcr.status = :status"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT pcr.id,
                           pcr.user_id,
                           submitter.display_name AS submitter_name,
                           pcr.changes,
                           pcr.old_values,
                           pcr.status,
                           pcr.machine_result,
                           pcr.reviewer_id,
                           reviewer.display_name AS reviewer_name,
                           pcr.review_comment,
                           pcr.created_at,
                           pcr.reviewed_at
                    FROM profile_change_request pcr
                    LEFT JOIN user_account submitter ON submitter.id = pcr.user_id
                    LEFT JOIN user_account reviewer ON reviewer.id = pcr.reviewer_id
                    WHERE pcr.status = :status
                    ORDER BY pcr.{sort_column} {sort_order}, pcr.id {sort_order}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_profile_review_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }
