from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.namespace.read import NamespaceReadError, get_namespace, list_my_namespaces, list_namespaces


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


def _parse_non_negative_int(value: int, default: int) -> int:
    return value if value >= 0 else default


def _parse_positive_int(value: int, default: int) -> int:
    return value if value > 0 else default


@router.get("/api/v1/namespaces")
@router.get("/api/web/namespaces")
async def list_namespaces_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "namespace_list_reader", None)
    normalized_page = _parse_non_negative_int(page, 0)
    normalized_size = _parse_positive_int(size, 20)
    data = await _resolve_result(
        reader(user_id, normalized_page, normalized_size)
        if reader is not None
        else list_namespaces(request.app.state.db_engine, user_id=user_id, page=normalized_page, size=normalized_size)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/me/namespaces")
@router.get("/api/web/me/namespaces")
async def list_my_namespaces_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "my_namespace_reader", None)
    data = await _resolve_result(
        reader(user_id) if reader is not None else list_my_namespaces(request.app.state.db_engine, user_id=user_id)
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/namespaces/{slug}")
@router.get("/api/web/namespaces/{slug}")
async def get_namespace_route(
    request: Request,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "namespace_detail_reader", None)
    try:
        data = await _resolve_result(
            reader(slug, user_id)
            if reader is not None
            else get_namespace(request.app.state.db_engine, slug=slug, user_id=user_id)
        )
    except NamespaceReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)
