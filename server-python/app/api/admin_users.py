from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.admin.users import (
    AdminUserError,
    list_admin_users,
    require_user_admin,
    trigger_admin_password_reset,
    update_admin_user_role,
    update_admin_user_status,
)
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import platform_roles
from app.core.response import ok


router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_current_user(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = await resolve_current_user_or_401(request, mock_user_id, authorization)
    return dict(user)


async def _require_admin_user(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = await _read_current_user(request, mock_user_id, authorization)
    try:
        require_user_admin(platform_roles(user))
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return user


def _roles(user: dict[str, Any]) -> list[str]:
    return platform_roles(user)


@router.get("/api/v1/admin/users")
async def list_admin_users_route(
    request: Request,
    search: str | None = None,
    status: str | None = None,
    page: int = Query(default=0),
    size: int = Query(default=20),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    reader = getattr(request.app.state, "admin_user_reader", None)
    payload = {"search": search, "status": status, "page": page, "size": size}
    try:
        data = await _resolve_result(
            reader(payload, user)
            if reader is not None
            else list_admin_users(
                request.app.state.db_engine,
                search=search,
                status=status,
                page=page,
                size=size,
                platform_roles=_roles(user),
            )
        )
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/admin/users/{user_id}/role")
async def update_admin_user_role_route(
    request: Request,
    user_id: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    writer = getattr(request.app.state, "admin_user_role_writer", None)
    try:
        data = await _resolve_result(
            writer(user_id, payload, user)
            if writer is not None
            else update_admin_user_role(
                request.app.state.db_engine,
                user_id=user_id,
                role=str(payload.get("role") or ""),
                actor_platform_roles=_roles(user),
            )
        )
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def _update_status_response(
    request: Request,
    user_id: str,
    status: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    writer = getattr(request.app.state, "admin_user_status_writer", None)
    payload = {"status": status}
    try:
        data = await _resolve_result(
            writer(user_id, payload, user)
            if writer is not None
            else update_admin_user_status(request.app.state.db_engine, user_id=user_id, status=status)
        )
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.put("/api/v1/admin/users/{user_id}/status")
async def update_admin_user_status_route(
    request: Request,
    user_id: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    return await _update_status_response(request, user_id, str(payload.get("status") or ""), user)


@router.post("/api/v1/admin/users/{user_id}/approve")
async def approve_admin_user_route(
    request: Request,
    user_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    return await _update_status_response(request, user_id, "ACTIVE", user)


@router.post("/api/v1/admin/users/{user_id}/disable")
async def disable_admin_user_route(
    request: Request,
    user_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    return await _update_status_response(request, user_id, "DISABLED", user)


@router.post("/api/v1/admin/users/{user_id}/enable")
async def enable_admin_user_route(
    request: Request,
    user_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    return await _update_status_response(request, user_id, "ACTIVE", user)


@router.post("/api/v1/admin/users/{user_id}/password-reset")
async def trigger_admin_user_password_reset_route(
    request: Request,
    user_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_admin_user(request, x_mock_user_id, authorization)
    writer = getattr(request.app.state, "admin_user_password_reset_writer", None)
    sender = getattr(request.app.state, "admin_password_reset_sender", None)
    try:
        await _resolve_result(
            writer(user_id, user)
            if writer is not None
            else trigger_admin_password_reset(
                request.app.state.db_engine,
                user_id=user_id,
                admin_user_id=str(user["userId"]),
                actor_platform_roles=_roles(user),
                sender=sender,
            )
        )
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5982\u679c\u8d26\u53f7\u7b26\u5408\u6761\u4ef6\uff0c\u5bc6\u7801\u91cd\u7f6e\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001\u3002", None, request)
