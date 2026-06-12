from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from app.auth.context import resolve_current_user_or_401
from app.auth.policy import require_api_token_scope
from app.auth.tokens import (
    ApiTokenError,
    create_api_token,
    list_api_tokens,
    revoke_api_token,
    update_api_token_expiration,
)
from app.core.response import ok

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _current_user(request: Request, mock_user_id: str | None, authorization: str | None) -> dict[str, Any]:
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_api_token_scope(user, "token:manage")
    return user


def _user_id(user: dict[str, Any]) -> str:
    return str(user.get("userId") or user.get("id") or "")


@router.post("/api/v1/tokens")
async def create_token_route(
    request: Request,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_user(request, x_mock_user_id, authorization)
    creator = getattr(request.app.state, "token_creator", None)
    try:
        data = await _resolve_result(
            creator(payload, user)
            if creator is not None
            else create_api_token(
                request.app.state.db_engine,
                user_id=_user_id(user),
                name=payload.get("name"),
                scopes=payload.get("scopes"),
                expires_at=payload.get("expiresAt"),
            )
        )
    except ApiTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.get("/api/v1/tokens")
async def list_tokens_route(
    request: Request,
    page: int = Query(default=0),
    size: int = Query(default=10),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_user(request, x_mock_user_id, authorization)
    lister = getattr(request.app.state, "token_lister", None)
    payload = {"page": page, "size": size}
    data = await _resolve_result(
        lister(payload, user)
        if lister is not None
        else list_api_tokens(request.app.state.db_engine, user_id=_user_id(user), page=page, size=size)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.delete("/api/v1/tokens/{token_id}", status_code=204)
async def revoke_token_route(
    request: Request,
    token_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    user = await _current_user(request, x_mock_user_id, authorization)
    revoker = getattr(request.app.state, "token_revoker", None)
    await _resolve_result(
        revoker(token_id, user)
        if revoker is not None
        else revoke_api_token(request.app.state.db_engine, user_id=_user_id(user), token_id=token_id)
    )
    return Response(status_code=204)


@router.put("/api/v1/tokens/{token_id}/expiration")
async def update_token_expiration_route(
    request: Request,
    token_id: int,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_user(request, x_mock_user_id, authorization)
    updater = getattr(request.app.state, "token_expiration_updater", None)
    try:
        data = await _resolve_result(
            updater(token_id, payload, user)
            if updater is not None
            else update_api_token_expiration(
                request.app.state.db_engine,
                user_id=_user_id(user),
                token_id=token_id,
                expires_at=payload.get("expiresAt"),
            )
        )
    except ApiTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)
