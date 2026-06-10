from __future__ import annotations

from typing import Any

from sqlalchemy import text


NOTIFICATION_CATEGORIES = ("PUBLISH", "REVIEW", "PROMOTION", "REPORT")
VALID_CHANNELS = {"IN_APP"}
SUPPORTED_CHANNEL = "IN_APP"


class NotificationPreferenceError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_category(value: Any) -> str:
    category = str(value)
    if category not in NOTIFICATION_CATEGORIES:
        raise NotificationPreferenceError("error.notification.preference.category.invalid", status_code=400)
    return category


def _normalize_channel(value: Any) -> str:
    channel = str(value)
    if channel not in VALID_CHANNELS:
        raise NotificationPreferenceError("error.notification.preference.channel.invalid", status_code=400)
    return channel


def _build_preference_response(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saved = {
        str(row["category"]): bool(row["enabled"])
        for row in rows
        if str(row.get("channel")) == SUPPORTED_CHANNEL
    }
    return [
        {"category": category, "channel": SUPPORTED_CHANNEL, "enabled": saved.get(category, True)}
        for category in NOTIFICATION_CATEGORIES
    ]


async def get_notification_preferences(engine: Any, user_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT category, channel, enabled
                    FROM notification_preference
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().all()
    return _build_preference_response([dict(row) for row in rows])


def _normalize_commands(preferences: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if preferences is None:
        raise NotificationPreferenceError("error.notification.preference.request.invalid", status_code=400)

    commands: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in preferences:
        category = _normalize_category(item.get("category") if isinstance(item, dict) else None)
        channel = _normalize_channel(item.get("channel") if isinstance(item, dict) else None)
        key = (category, channel)
        if key in seen:
            raise NotificationPreferenceError("error.notification.preference.duplicate", status_code=400)
        seen.add(key)
        commands.append({"category": category, "channel": channel, "enabled": bool(item.get("enabled"))})
    return commands


async def update_notification_preferences(
    engine: Any,
    user_id: str,
    preferences: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    commands = _normalize_commands(preferences)
    async with engine.begin() as connection:
        for command in commands:
            await connection.execute(
                text(
                    """
                    INSERT INTO notification_preference (user_id, category, channel, enabled)
                    VALUES (:user_id, :category, :channel, :enabled)
                    ON CONFLICT (user_id, category, channel)
                    DO UPDATE SET enabled = EXCLUDED.enabled
                    """
                ),
                {
                    "user_id": user_id,
                    "category": command["category"],
                    "channel": command["channel"],
                    "enabled": command["enabled"],
                },
            )
    return await get_notification_preferences(engine, user_id)
