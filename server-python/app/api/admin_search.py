from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.admin.search import AdminSearchError, rebuild_search_index
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.api.auth import read_current_mock_user
from app.core.response import ok

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _require_super_admin_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    user = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    data = dict(user)
    if "SUPER_ADMIN" not in {str(role) for role in data.get("platformRoles", [])}:
        raise HTTPException(status_code=403, detail="admin.search.no_permission")
    return data


def _request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.state.request_id,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.post("/api/v1/admin/search/rebuild")
async def rebuild_admin_search_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "admin_search_rebuild_writer", None)
    context = _request_context(request)
    try:
        if writer is not None:
            await _resolve_result(writer(user, context))
        else:
            await rebuild_search_index(
                request.app.state.db_engine,
                actor_user_id=str(user["userId"]),
                platform_roles=[str(role) for role in user.get("platformRoles", [])],
                **context,
            )
    except AdminSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)
