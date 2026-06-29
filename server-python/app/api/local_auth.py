from __future__ import annotations

import os
from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.auth.context import resolve_current_user_or_401
from app.auth.local import LocalAuthError, change_local_password, login_local_user, register_local_user
from app.auth.password_reset import (
    PasswordResetError,
    confirm_password_reset,
    request_password_reset,
    validate_password_reset_confirm,
    validate_password_reset_request,
)
from app.auth.session import establish_session
from app.core.config import parse_bool
from app.core.response import ok

router = APIRouter()


def _as_bool(value: bool | str) -> bool:
    if isinstance(value, str):
        return parse_bool(value, True)
    return value


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _local_registration_enabled(request: Request) -> bool:
    app_state_value = getattr(request.app.state, "local_registration_enabled", None)
    if app_state_value is not None:
        return _as_bool(app_state_value)

    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        return _as_bool(getattr(settings, "local_registration_enabled", True))

    return parse_bool(os.getenv("SKILLHUB_LOCAL_REGISTRATION_ENABLED"), True)


@router.post("/api/v1/auth/local/register")
async def register_local_account_route(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    if not _local_registration_enabled(request):
        raise HTTPException(status_code=403, detail="error.auth.local.registrationDisabled")

    registrar = getattr(request.app.state, "local_auth_registrar", None)
    try:
        data = await _resolve_result(
            registrar(payload)
            if registrar is not None
            else register_local_user(
                request.app.state.db_engine,
                username=payload.get("username"),
                password=payload.get("password"),
                email=payload.get("email"),
            )
        )
    except LocalAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    await establish_session(request, response, data)
    return ok("response.success.created", data, request)


@router.post("/api/v1/auth/local/login")
async def login_local_account_route(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    login = getattr(request.app.state, "local_auth_login", None)
    try:
        data = await _resolve_result(
            login(payload)
            if login is not None
            else login_local_user(
                request.app.state.db_engine,
                username=payload.get("username"),
                password=payload.get("password"),
            )
        )
    except LocalAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    await establish_session(request, response, data)
    return ok("response.success.read", data, request)


@router.post("/api/v1/auth/local/change-password")
async def change_local_password_route(
    request: Request,
    payload: dict[str, Any],
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await resolve_current_user_or_401(request, mock_user_id, authorization)
    user_id = str(user["userId"])
    changer = getattr(request.app.state, "local_auth_password_changer", None)
    try:
        await _resolve_result(
            changer(user_id, payload)
            if changer is not None
            else change_local_password(
                request.app.state.db_engine,
                user_id=user_id,
                current_password=payload.get("currentPassword"),
                new_password=payload.get("newPassword"),
            )
        )
    except LocalAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.updated", None, request)


@router.post("/api/v1/auth/local/password-reset/request")
async def request_local_password_reset_route(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    requester = getattr(request.app.state, "local_password_reset_requester", None)
    sender = getattr(request.app.state, "local_password_reset_sender", None)
    try:
        validate_password_reset_request(payload.get("email"))
        await _resolve_result(
            requester(payload)
            if requester is not None
            else request_password_reset(
                request.app.state.db_engine,
                email=payload.get("email"),
                sender=sender,
            )
        )
    except PasswordResetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5982\u679c\u8d26\u53f7\u7b26\u5408\u6761\u4ef6\uff0c\u5bc6\u7801\u91cd\u7f6e\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001\u3002", None, request)


@router.post("/api/v1/auth/local/password-reset/confirm")
async def confirm_local_password_reset_route(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    confirmer = getattr(request.app.state, "local_password_reset_confirmer", None)
    try:
        validate_password_reset_confirm(payload.get("email"), payload.get("code"), payload.get("newPassword"))
        await _resolve_result(
            confirmer(payload)
            if confirmer is not None
            else confirm_password_reset(
                request.app.state.db_engine,
                email=payload.get("email"),
                code=payload.get("code"),
                new_password=payload.get("newPassword"),
            )
        )
    except PasswordResetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5bc6\u7801\u5df2\u91cd\u7f6e\u3002", None, request)
