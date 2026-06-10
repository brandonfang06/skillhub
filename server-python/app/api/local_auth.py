from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.auth.password_reset import (
    PasswordResetError,
    confirm_password_reset,
    request_password_reset,
    validate_password_reset_confirm,
    validate_password_reset_request,
)
from app.core.response import ok

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


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
