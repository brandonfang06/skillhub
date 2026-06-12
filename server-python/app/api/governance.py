from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import read_current_mock_user
from app.core.response import ok
from app.governance.workbench import (
    GovernanceWorkbenchError,
    get_governance_summary,
    list_governance_activity,
    list_governance_inbox,
    list_governance_notifications,
    mark_governance_notification_read,
)


router = APIRouter()


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


def _page(value: int) -> int:
    return max(0, int(value))


def _size(value: int) -> int:
    return int(value) if int(value) > 0 else 20


@router.get("/api/v1/governance/summary")
@router.get("/api/web/governance/summary")
async def governance_summary_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "governance_summary_reader", None)
    data = await _resolve_result(
        reader(user_id) if reader is not None else get_governance_summary(request.app.state.db_engine, user_id=user_id)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/governance/inbox")
@router.get("/api/web/governance/inbox")
async def governance_inbox_route(
    request: Request,
    type: str | None = None,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "governance_inbox_reader", None)
    try:
        data = await _resolve_result(
            reader({"type": type, "page": _page(page), "size": _size(size)}, user_id)
            if reader is not None
            else list_governance_inbox(
                request.app.state.db_engine,
                user_id=user_id,
                type_filter=type,
                page=_page(page),
                size=_size(size),
            )
        )
    except GovernanceWorkbenchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/governance/activity")
@router.get("/api/web/governance/activity")
async def governance_activity_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "governance_activity_reader", None)
    data = await _resolve_result(
        reader({"page": _page(page), "size": _size(size)}, user_id)
        if reader is not None
        else list_governance_activity(
            request.app.state.db_engine,
            user_id=user_id,
            page=_page(page),
            size=_size(size),
        )
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/governance/notifications")
@router.get("/api/web/governance/notifications")
async def governance_notifications_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "governance_notification_reader", None)
    data = await _resolve_result(
        reader({"page": _page(page), "size": _size(size)}, user_id)
        if reader is not None
        else list_governance_notifications(
            request.app.state.db_engine,
            user_id=user_id,
            page=_page(page),
            size=_size(size),
        )
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.post("/api/v1/governance/notifications/{notification_id}/read")
@router.post("/api/web/governance/notifications/{notification_id}/read")
async def governance_notification_mark_read_route(
    notification_id: int,
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "governance_notification_mark_read_writer", None)
    try:
        data = await _resolve_result(
            writer(notification_id, user_id)
            if writer is not None
            else mark_governance_notification_read(
                request.app.state.db_engine,
                notification_id=notification_id,
                user_id=user_id,
            )
        )
    except GovernanceWorkbenchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)
