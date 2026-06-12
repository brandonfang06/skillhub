from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.notifications import format_sse_comment, format_sse_event
from app.notifications.fanout import NotificationFanoutManager
from app.notifications.publisher import build_notification_sse_payload


async def _connected() -> bool:
    return False


@pytest.mark.anyio
async def test_fanout_stream_emits_connected_heartbeat_and_user_scoped_notifications() -> None:
    manager = NotificationFanoutManager()
    user_stream = manager.stream("user-1", is_disconnected=_connected, heartbeat_interval=0.25)
    other_stream = manager.stream("user-2", is_disconnected=_connected, heartbeat_interval=0.25)

    assert await anext(user_stream) == format_sse_event("connected", "ok")
    assert await anext(other_stream) == format_sse_event("connected", "ok")
    assert manager.connection_count("user-1") == 1
    assert manager.connection_count("user-2") == 1

    await manager.publish("user-1", {"id": 7, "title": "Ready"})

    assert await anext(user_stream) == format_sse_event("notification", '{"id":7,"title":"Ready"}')
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(anext(other_stream), timeout=0.03)

    assert await anext(user_stream) == format_sse_comment("ping")

    await user_stream.aclose()
    await other_stream.aclose()
    assert manager.total_connections() == 0


@pytest.mark.anyio
async def test_fanout_evicts_oldest_user_stream_when_user_limit_is_exceeded() -> None:
    manager = NotificationFanoutManager(max_connections_per_user=1)
    first = manager.stream("user-1", is_disconnected=_connected, heartbeat_interval=0.25)
    second = manager.stream("user-1", is_disconnected=_connected, heartbeat_interval=0.25)

    assert await anext(first) == format_sse_event("connected", "ok")
    assert await anext(second) == format_sse_event("connected", "ok")

    await manager.publish("user-1", {"id": 8})

    with pytest.raises(StopAsyncIteration):
        await anext(first)
    assert await anext(second) == format_sse_event("notification", '{"id":8}')

    await second.aclose()


def test_notification_sse_payload_matches_java_dispatcher_shape() -> None:
    payload = build_notification_sse_payload(
        {
            "id": 11,
            "recipient_id": "user-1",
            "category": "REPORT",
            "event_type": "REPORT_SUBMITTED",
            "title": "Skill reported",
            "body_json": None,
            "entity_type": "REPORT",
            "entity_id": 901,
            "created_at": datetime(2026, 6, 12, 8, 30, tzinfo=UTC),
        }
    )

    assert payload == {
        "id": 11,
        "category": "REPORT",
        "eventType": "REPORT_SUBMITTED",
        "title": "Skill reported",
        "bodyJson": "",
        "entityType": "REPORT",
        "entityId": 901,
        "createdAt": "2026-06-12T08:30:00Z",
    }
