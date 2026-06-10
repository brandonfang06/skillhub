from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.notifications.service import (
    NotificationError,
    delete_read_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
)
from app.notifications.preferences import (
    NotificationPreferenceError,
    get_notification_preferences,
    update_notification_preferences,
)


router = APIRouter()

SSE_HEARTBEAT_INTERVAL_SECONDS = 30


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _require_user_id(request: Request, mock_user_id: str | None) -> str:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(data["userId"])


def _parse_non_negative_int(value: int, default: int) -> int:
    return value if value >= 0 else default


def _parse_positive_int(value: int, default: int) -> int:
    return value if value > 0 else default


def _escape_sse_lines(value: str) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def format_sse_event(event: str, data: str) -> str:
    event_name = _escape_sse_lines(event).split("\n", 1)[0]
    payload = "".join(f"data: {line}\n" for line in _escape_sse_lines(data).split("\n"))
    return f"event: {event_name}\n{payload}\n"


def format_sse_comment(comment: str) -> str:
    line = _escape_sse_lines(comment).split("\n", 1)[0]
    return f": {line}\n\n"


async def default_notification_sse_stream(user_id: str, request: Request):
    yield format_sse_event("connected", "ok")
    while not await request.is_disconnected():
        await asyncio.sleep(SSE_HEARTBEAT_INTERVAL_SECONDS)
        yield format_sse_comment("ping")


@router.get("/api/v1/notifications/sse")
@router.get("/api/web/notifications/sse")
async def notification_sse_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> StreamingResponse:
    user_id = await _require_user_id(request, x_mock_user_id)
    stream_factory = getattr(request.app.state, "notification_sse_stream_factory", None)
    stream = (
        stream_factory(user_id)
        if stream_factory is not None
        else default_notification_sse_stream(user_id, request)
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v1/notifications")
@router.get("/api/web/notifications")
async def list_notifications_route(
    request: Request,
    category: str | None = None,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "notification_list_reader", None)
    try:
        data = await _resolve_result(
            reader(user_id, category, _parse_non_negative_int(page, 0), _parse_positive_int(size, 20))
            if reader is not None
            else list_notifications(
                request.app.state.db_engine,
                user_id=user_id,
                category=category,
                page=_parse_non_negative_int(page, 0),
                size=_parse_positive_int(size, 20),
            )
        )
    except NotificationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/notifications/unread-count")
@router.get("/api/web/notifications/unread-count")
async def unread_count_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "notification_unread_count_reader", None)
    data = await _resolve_result(
        reader(user_id)
        if reader is not None
        else unread_notification_count(request.app.state.db_engine, user_id)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/notifications/{notification_id}/read")
@router.put("/api/web/notifications/{notification_id}/read")
async def mark_read_route(
    request: Request,
    notification_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "notification_mark_read_writer", None)
    try:
        await _resolve_result(
            writer(notification_id, user_id)
            if writer is not None
            else mark_notification_read(request.app.state.db_engine, notification_id=notification_id, user_id=user_id)
        )
    except NotificationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


@router.put("/api/v1/notifications/read-all")
@router.put("/api/web/notifications/read-all")
async def mark_all_read_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "notification_mark_all_read_writer", None)
    data = await _resolve_result(
        writer(user_id)
        if writer is not None
        else mark_all_notifications_read(request.app.state.db_engine, user_id)
    )
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/notifications/{notification_id}")
@router.delete("/api/web/notifications/{notification_id}")
async def delete_read_route(
    request: Request,
    notification_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "notification_delete_read_writer", None)
    try:
        await _resolve_result(
            writer(notification_id, user_id)
            if writer is not None
            else delete_read_notification(request.app.state.db_engine, notification_id=notification_id, user_id=user_id)
        )
    except NotificationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", None, request)


@router.get("/api/v1/notification-preferences")
@router.get("/api/web/notification-preferences")
async def get_notification_preferences_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "notification_preference_reader", None)
    data = await _resolve_result(
        reader(user_id)
        if reader is not None
        else get_notification_preferences(request.app.state.db_engine, user_id)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/notification-preferences")
@router.put("/api/web/notification-preferences")
async def update_notification_preferences_route(
    request: Request,
    payload: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "notification_preference_writer", None)
    preferences = payload.get("preferences") if isinstance(payload, dict) else None
    try:
        if preferences is None:
            raise NotificationPreferenceError("error.notification.preference.request.invalid", status_code=400)
        data = await _resolve_result(
            writer(user_id, preferences)
            if writer is not None
            else update_notification_preferences(request.app.state.db_engine, user_id, preferences)
        )
    except NotificationPreferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)
