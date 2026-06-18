from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text

from app.auth.context import resolve_current_user_or_401
from app.auth.device import (
    DeviceAuthError,
    RedisDeviceStore,
    authorize_device_code,
    generate_device_code,
    poll_device_token,
)
from app.core.response import ok
from app.core.redis import create_redis_client

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _redis(request: Request) -> RedisDeviceStore:
    configured = getattr(request.app.state, "device_auth_redis", None)
    if configured is not None:
        return configured
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        redis_client = create_redis_client(request.app.state.settings)
        request.app.state.redis_client = redis_client
    return RedisDeviceStore(redis_client)


async def record_device_authorize_audit(
    engine: Any,
    *,
    actor_user_id: str,
    user_code: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    actor_user_id, action, target_type, target_id, request_id,
                    client_ip, user_agent, detail_json, created_at
                )
                VALUES (
                    :actor_user_id, :action, :target_type, :target_id, :request_id,
                    :client_ip, :user_agent, :detail_json, :created_at
                )
                """
            ),
            {
                "actor_user_id": actor_user_id,
                "action": "DEVICE_AUTHORIZE",
                "target_type": "DEVICE_CODE",
                "target_id": None,
                "request_id": request_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "detail_json": json.dumps({"userCode": "" if user_code is None else str(user_code)}, separators=(",", ":")),
                "created_at": datetime.now(UTC),
            },
        )


@router.post("/api/v1/auth/device/code")
async def request_device_code_route(request: Request) -> dict[str, Any]:
    generator = getattr(request.app.state, "device_code_generator", None)
    try:
        data = await _resolve_result(
            generator()
            if generator is not None
            else generate_device_code(
                _redis(request),
                verification_uri=getattr(request.app.state.settings, "device_auth_verification_uri", "/cli/auth"),
            )
        )
    except DeviceAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.created", data, request)


@router.post("/api/v1/device/authorize")
async def authorize_device_route(
    request: Request,
    payload: dict[str, Any],
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await resolve_current_user_or_401(request, mock_user_id, None)
    user_id = str(user["userId"])
    authorizer = getattr(request.app.state, "device_code_authorizer", None)
    try:
        await _resolve_result(
            authorizer(user_id, payload, request)
            if authorizer is not None
            else authorize_device_code(_redis(request), user_code=payload.get("userCode"), user_id=user_id)
        )
        audit_writer = getattr(request.app.state, "device_authorize_audit_writer", None)
        if audit_writer is not None:
            await _resolve_result(audit_writer(user_id, payload, request))
        else:
            await record_device_authorize_audit(
                request.app.state.db_engine,
                actor_user_id=user_id,
                user_code=payload.get("userCode"),
                request_id=getattr(request.state, "request_id", None),
                client_ip=request.client.host if request.client is not None else None,
                user_agent=request.headers.get("user-agent"),
            )
    except DeviceAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.updated", {"message": "Device authorized successfully"}, request)


@router.post("/api/v1/auth/device/token")
async def poll_device_token_route(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    poller = getattr(request.app.state, "device_token_poller", None)
    try:
        data = await _resolve_result(
            poller(payload)
            if poller is not None
            else poll_device_token(
                _redis(request),
                request.app.state.db_engine,
                device_code=payload.get("deviceCode"),
            )
        )
    except DeviceAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)
