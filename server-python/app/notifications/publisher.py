from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol


class NotificationFanout(Protocol):
    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        ...


def _java_instant(value: Any) -> str:
    if isinstance(value, datetime):
        instant = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def build_notification_sse_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "category": str(row["category"]),
        "eventType": str(row["event_type"]),
        "title": str(row["title"]),
        "bodyJson": row.get("body_json") if row.get("body_json") is not None else "",
        "entityType": row.get("entity_type") if row.get("entity_type") is not None else "",
        "entityId": int(row["entity_id"]) if row.get("entity_id") is not None else 0,
        "createdAt": _java_instant(row["created_at"]),
    }


async def publish_notification_rows(fanout: NotificationFanout | None, rows: list[dict[str, Any]]) -> None:
    if fanout is None:
        return
    for row in rows:
        await fanout.publish(str(row["recipient_id"]), build_notification_sse_payload(row))
