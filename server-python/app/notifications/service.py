from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import text


VALID_CATEGORIES = {"PUBLISH", "REVIEW", "PROMOTION", "REPORT"}


class NotificationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _to_java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.isoformat().replace("+00:00", "Z")
    text_value = str(value)
    return text_value.replace("+00:00", "Z")


def _parse_body_json(value: str | None) -> dict[str, Any]:
    if value is None or value.strip() == "":
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _resolve_target(row: dict[str, Any]) -> dict[str, Any]:
    event_type = row.get("event_type")
    entity_type = row.get("entity_type")
    entity_id = row.get("entity_id")
    body = _parse_body_json(row.get("body_json"))
    namespace = body.get("namespace") if isinstance(body.get("namespace"), str) else None
    slug = body.get("slug") if isinstance(body.get("slug"), str) else None

    if event_type == "REVIEW_SUBMITTED" and entity_id is not None:
        return {"targetType": "REVIEW", "targetId": int(entity_id), "targetRoute": f"/dashboard/reviews/{entity_id}"}
    if event_type == "PROMOTION_SUBMITTED":
        return {"targetType": "PROMOTION", "targetId": int(entity_id) if entity_id is not None else None, "targetRoute": "/dashboard/promotions"}
    if event_type == "REPORT_SUBMITTED":
        return {"targetType": "REPORT", "targetId": int(entity_id) if entity_id is not None else None, "targetRoute": "/dashboard/reports"}
    if namespace is not None and slug is not None and (entity_type == "SKILL" or row.get("category") == "PUBLISH"):
        return {"targetType": "SKILL", "targetId": int(entity_id) if entity_id is not None else None, "targetRoute": f"/space/{namespace}/{slug}"}
    return {
        "targetType": entity_type,
        "targetId": int(entity_id) if entity_id is not None else None,
        "targetRoute": "/dashboard/notifications",
    }


def build_notification_response(row: dict[str, Any]) -> dict[str, Any]:
    target = _resolve_target(row)
    return {
        "id": int(row["id"]),
        "category": str(row["category"]),
        "eventType": str(row["event_type"]),
        "title": str(row["title"]),
        "bodyJson": row.get("body_json"),
        "entityType": row.get("entity_type"),
        "entityId": int(row["entity_id"]) if row.get("entity_id") is not None else None,
        "status": str(row["status"]),
        "createdAt": _to_java_instant(row.get("created_at")),
        "readAt": _to_java_instant(row.get("read_at")),
        **target,
    }


def _normalize_category(category: str | None) -> str | None:
    if category is None or category.strip() == "":
        return None
    normalized = category.strip()
    if normalized not in VALID_CATEGORIES:
        raise NotificationError("error.notification.category.invalid", status_code=400)
    return normalized


async def list_notifications(
    engine: Any,
    *,
    user_id: str,
    category: str | None,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized_category = _normalize_category(category)
    filters = ["recipient_id = :recipient_id"]
    params: dict[str, Any] = {"recipient_id": user_id, "limit": size, "offset": page * size}
    if normalized_category is not None:
        filters.append("category = :category")
        params["category"] = normalized_category
    where_sql = " AND ".join(filters)

    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(f"SELECT COUNT(*) FROM notification WHERE {where_sql}"),
                params,
            )
        ).scalar_one()
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT id, recipient_id, category, event_type, title, body_json,
                           entity_type, entity_id, status, created_at, read_at
                    FROM notification
                    WHERE {where_sql}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()

    return {
        "items": [build_notification_response(dict(row)) for row in rows],
        "total": int(total),
        "page": page,
        "size": size,
    }


async def unread_notification_count(engine: Any, user_id: str) -> dict[str, int]:
    async with engine.connect() as connection:
        count = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM notification
                    WHERE recipient_id = :recipient_id
                      AND status = 'UNREAD'
                    """
                ),
                {"recipient_id": user_id},
            )
        ).scalar_one()
    return {"count": int(count)}


async def mark_notification_read(engine: Any, *, notification_id: int, user_id: str) -> dict[str, Any]:
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, recipient_id, category, event_type, title, body_json,
                           entity_type, entity_id, status, created_at, read_at
                    FROM notification
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": notification_id},
            )
        ).mappings().all()
        if not rows:
            raise NotificationError("error.notification.notFound", status_code=404)
        existing = dict(rows[0])
        if str(existing["recipient_id"]) != str(user_id):
            raise NotificationError("error.notification.noPermission", status_code=403)

        updated_rows = (
            await connection.execute(
                text(
                    """
                    UPDATE notification
                    SET status = 'READ',
                        read_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    RETURNING id, recipient_id, category, event_type, title, body_json,
                              entity_type, entity_id, status, created_at, read_at
                    """
                ),
                {"id": notification_id},
            )
        ).mappings().all()
    return build_notification_response(dict(updated_rows[0]))


async def mark_all_notifications_read(engine: Any, user_id: str) -> dict[str, int]:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                """
                UPDATE notification
                SET status = 'READ',
                    read_at = CURRENT_TIMESTAMP
                WHERE recipient_id = :recipient_id
                  AND status = 'UNREAD'
                """
            ),
            {"recipient_id": user_id},
        )
    return {"updated": int(result.rowcount or 0)}


async def delete_read_notification(engine: Any, *, notification_id: int, user_id: str) -> None:
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                """
                DELETE FROM notification
                WHERE id = :id
                  AND recipient_id = :recipient_id
                  AND status = 'READ'
                """
            ),
            {"id": notification_id, "recipient_id": user_id},
        )
    if int(result.rowcount or 0) == 0:
        raise NotificationError("error.notification.readNotFound", status_code=400)
