from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.admin.audit_logs import AdminAuditLogError, list_admin_audit_logs, require_audit_reader
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import platform_roles
from app.core.response import ok


router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _require_audit_user(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = await resolve_current_user_or_401(request, mock_user_id, authorization)
    try:
        require_audit_reader(platform_roles(dict(user)))
    except AdminAuditLogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return dict(user)


@router.get("/api/v1/admin/audit-logs")
async def list_admin_audit_logs_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    userId: str | None = None,
    action: str | None = None,
    requestId: str | None = None,
    ipAddress: str | None = None,
    resourceType: str | None = None,
    resourceId: str | None = None,
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_audit_user(request, x_mock_user_id, authorization)
    payload = {
        "page": page,
        "size": size,
        "userId": userId,
        "action": action,
        "requestId": requestId,
        "ipAddress": ipAddress,
        "resourceType": resourceType,
        "resourceId": resourceId,
        "startTime": startTime,
        "endTime": endTime,
    }
    reader = getattr(request.app.state, "admin_audit_log_reader", None)
    data = await _resolve_result(
        reader(payload, user)
        if reader is not None
        else list_admin_audit_logs(
            request.app.state.db_engine,
            page=page,
            size=size,
            user_id=userId,
            action=action,
            request_id=requestId,
            ip_address=ipAddress,
            resource_type=resourceType,
            resource_id=resourceId,
            start_time=startTime,
            end_time=endTime,
            platform_roles=platform_roles(user),
        )
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)
