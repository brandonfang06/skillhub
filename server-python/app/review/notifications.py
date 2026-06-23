from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.notifications.publisher import NotificationFanout, publish_notification_rows


REVIEW_NOTIFICATION_CATEGORY = "REVIEW"


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def _skill_name(name: str | None, slug: str) -> str:
    if name is not None and name.strip() != "":
        return name
    return slug


async def read_review_submission_recipients(connection: Any, *, namespace_id: int) -> list[str]:
    namespace_rows = (
        await connection.execute(
            text(
                """
                SELECT DISTINCT nm.user_id
                FROM namespace_member nm
                LEFT JOIN notification_preference np
                  ON np.user_id = nm.user_id
                 AND np.category = 'REVIEW'
                 AND np.channel = 'IN_APP'
                WHERE nm.namespace_id = :namespace_id
                  AND nm.role IN ('OWNER', 'ADMIN')
                  AND COALESCE(np.enabled, TRUE) = TRUE
                ORDER BY nm.user_id
                """
            ),
            {"namespace_id": namespace_id},
        )
    ).mappings().all()
    return list(dict.fromkeys([str(row["user_id"]) for row in namespace_rows]))


async def _in_app_review_notifications_enabled(connection: Any, user_id: str) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT COALESCE(np.enabled, TRUE) AS enabled
                FROM (SELECT :user_id AS user_id) target
                LEFT JOIN notification_preference np
                  ON np.user_id = target.user_id
                 AND np.category = 'REVIEW'
                 AND np.channel = 'IN_APP'
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return True if row is None else bool(row["enabled"])


async def _insert_review_notification(
    connection: Any,
    *,
    recipient_id: str,
    event_type: str,
    title: str,
    body_json: str,
    entity_type: str,
    entity_id: int,
    created_at: datetime,
) -> list[dict[str, Any]]:
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
                "recipient_id": recipient_id,
                "category": REVIEW_NOTIFICATION_CATEGORY,
                "event_type": event_type,
                "title": title,
                "body_json": body_json,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "status": "UNREAD",
                "created_at": created_at,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def write_review_submitted_notifications(
    connection: Any,
    *,
    recipients: list[str],
    review_task_id: int,
    skill_id: int,
    version_id: int,
    submitter_id: str,
    namespace: str,
    slug: str,
    skill_name: str | None,
    version: str,
    created_at: datetime,
) -> list[dict[str, Any]]:
    created_rows: list[dict[str, Any]] = []
    display_name = _skill_name(skill_name, slug)
    body_json = _json_dumps(
        {
            "reviewId": review_task_id,
            "skillId": skill_id,
            "versionId": version_id,
            "submitterId": submitter_id,
            "namespace": namespace,
            "slug": slug,
            "skillName": display_name,
            "version": version,
        }
    )
    for recipient_id in dict.fromkeys(recipients):
        created_rows.extend(
            await _insert_review_notification(
                connection,
                recipient_id=recipient_id,
                event_type="REVIEW_SUBMITTED",
                title=f"Review submitted: {display_name}",
                body_json=body_json,
                entity_type="REVIEW",
                entity_id=review_task_id,
                created_at=created_at,
            )
        )
    return created_rows


async def write_review_decision_notification(
    connection: Any,
    *,
    recipient_id: str,
    approved: bool,
    review_task_id: int,
    skill_id: int,
    version_id: int,
    reviewer_id: str,
    namespace: str,
    slug: str,
    skill_name: str | None,
    version: str,
    comment: str | None,
    created_at: datetime,
) -> list[dict[str, Any]]:
    if not await _in_app_review_notifications_enabled(connection, recipient_id):
        return []
    display_name = _skill_name(skill_name, slug)
    decision = "approved" if approved else "rejected"
    body: dict[str, Any] = {
        "reviewId": review_task_id,
        "skillId": skill_id,
        "versionId": version_id,
        "reviewerId": reviewer_id,
        "namespace": namespace,
        "slug": slug,
        "skillName": display_name,
        "version": version,
        "status": "APPROVED" if approved else "REJECTED",
    }
    if comment is not None and comment.strip() != "":
        body["comment"] = comment
    return await _insert_review_notification(
        connection,
        recipient_id=recipient_id,
        event_type="REVIEW_APPROVED" if approved else "REVIEW_REJECTED",
        title=f"Review {decision}: {display_name}",
        body_json=_json_dumps(body),
        entity_type="SKILL",
        entity_id=skill_id,
        created_at=created_at,
    )


async def publish_review_notifications(fanout: NotificationFanout | None, rows: list[dict[str, Any]]) -> None:
    await publish_notification_rows(fanout, rows)
