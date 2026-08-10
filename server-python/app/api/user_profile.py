from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import resolve_current_user_or_401
from app.core.request_id import request_id_from_request
from app.core.response import ok
from app.user_profile import (
    UserProfileError,
    get_user_profile,
    profile_human_review_enabled,
    profile_machine_review_enabled,
    update_user_profile,
)

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    data = await resolve_current_user_or_401(request, mock_user_id, None)
    return dict(data)


def _user_id(user: dict[str, Any]) -> str:
    value = user.get("userId") or user.get("id")
    if value is None or str(value).strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(value)


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first and first.lower() != "unknown":
            return first
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip() and real_ip.strip().lower() != "unknown":
        return real_ip.strip()
    return request.client.host if request.client else None


def _request_meta(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request_id_from_request(request),
        "client_ip": _client_ip(request),
        "user_agent": request.headers.get("User-Agent"),
    }


@router.get("/api/v1/user/profile")
async def get_user_profile_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _read_current_user(request, x_mock_user_id)
    user_id = _user_id(user)
    reader = getattr(request.app.state, "user_profile_reader", None)
    try:
        data = await _resolve_result(
            reader(user_id)
            if reader is not None
            else get_user_profile(
                request.app.state.db_engine,
                user_id,
                human_review=profile_human_review_enabled(getattr(request.app.state, "profile_human_review_enabled", None)),
            )
        )
    except UserProfileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.patch("/api/v1/user/profile")
async def update_user_profile_route(
    request: Request,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _read_current_user(request, x_mock_user_id)
    user_id = _user_id(user)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "user_profile_writer", None)
    try:
        data = await _resolve_result(
            writer(user_id, body if isinstance(body, dict) else {}, meta)
            if writer is not None
            else update_user_profile(
                request.app.state.db_engine,
                user_id=user_id,
                payload=body if isinstance(body, dict) else {},
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
                human_review=profile_human_review_enabled(getattr(request.app.state, "profile_human_review_enabled", None)),
                machine_review=profile_machine_review_enabled(getattr(request.app.state, "profile_machine_review_enabled", None)),
                notification_fanout=getattr(request.app.state, "notification_fanout", None),
            )
        )
    except UserProfileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.update", data, request)
