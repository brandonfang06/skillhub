from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.admin.labels import (
    AdminLabelError,
    create_label_definition,
    delete_label_definition,
    list_label_definitions,
    update_label_definition,
    update_label_sort_order,
)
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import read_current_mock_user
from app.auth.policy import platform_roles, require_platform_role
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
    require_platform_role(data, "SUPER_ADMIN", detail="label.definition.no_permission")
    return data


def _request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.state.request_id,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.get("/api/v1/admin/labels")
async def list_admin_labels_route(
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    reader = getattr(request.app.state, "admin_label_reader", None)
    try:
        data = await _resolve_result(
            reader(user)
            if reader is not None
            else list_label_definitions(request.app.state.db_engine, platform_roles=platform_roles(user))
        )
    except AdminLabelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.post("/api/v1/admin/labels")
async def create_admin_label_route(
    request: Request,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "admin_label_create_writer", None)
    try:
        data = await _resolve_result(
            writer(payload, user, request)
            if writer is not None
            else create_label_definition(
                request.app.state.db_engine,
                slug=str(payload.get("slug") or ""),
                type=str(payload.get("type") or ""),
                visible_in_filter=bool(payload.get("visibleInFilter")),
                sort_order=int(payload.get("sortOrder") or 0),
                translations=list(payload.get("translations") or []),
                actor_user_id=str(user["userId"]),
                platform_roles=platform_roles(user),
                **_request_context(request),
            )
        )
    except AdminLabelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.put("/api/v1/admin/labels/sort-order")
async def update_admin_label_sort_order_route(
    request: Request,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "admin_label_sort_writer", None)
    try:
        data = await _resolve_result(
            writer(payload, user, request)
            if writer is not None
            else update_label_sort_order(
                request.app.state.db_engine,
                items=list(payload.get("items") or []),
                actor_user_id=str(user["userId"]),
                platform_roles=platform_roles(user),
                **_request_context(request),
            )
        )
    except AdminLabelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.put("/api/v1/admin/labels/{slug}")
async def update_admin_label_route(
    request: Request,
    slug: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "admin_label_update_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, payload, user, request)
            if writer is not None
            else update_label_definition(
                request.app.state.db_engine,
                slug=slug,
                type=str(payload.get("type") or ""),
                visible_in_filter=bool(payload.get("visibleInFilter")),
                sort_order=int(payload.get("sortOrder") or 0),
                translations=list(payload.get("translations") or []),
                actor_user_id=str(user["userId"]),
                platform_roles=platform_roles(user),
                **_request_context(request),
            )
        )
    except AdminLabelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/admin/labels/{slug}")
async def delete_admin_label_route(
    request: Request,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_super_admin_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "admin_label_delete_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, user, request)
            if writer is not None
            else delete_label_definition(
                request.app.state.db_engine,
                slug=slug,
                actor_user_id=str(user["userId"]),
                platform_roles=platform_roles(user),
                **_request_context(request),
            )
        )
    except AdminLabelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)
