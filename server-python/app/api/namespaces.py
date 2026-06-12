from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import read_current_mock_user
from app.core.response import ok
from app.namespace.members import (
    NamespaceMemberReadError,
    add_namespace_member,
    batch_add_namespace_members,
    list_namespace_members,
    remove_namespace_member,
    search_namespace_member_candidates,
    transfer_namespace_ownership,
    update_namespace_member_role,
)
from app.namespace.mutations import (
    NamespaceMutationError,
    archive_namespace,
    create_namespace,
    delete_namespace,
    freeze_namespace,
    restore_namespace,
    unfreeze_namespace,
    update_namespace,
)
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


async def _require_current_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


def _parse_non_negative_int(value: int, default: int) -> int:
    return value if value >= 0 else default


def _parse_positive_int(value: int, default: int) -> int:
    return value if value > 0 else default


def _parse_candidate_size(value: int) -> int:
    if value <= 0:
        return 10
    return min(value, 20)


@router.post("/api/v1/namespaces")
@router.post("/api/web/namespaces")
async def create_namespace_route(
    request: Request,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _require_current_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_create_writer", None)
    try:
        data = await _resolve_result(
            writer(payload, user)
            if writer is not None
            else create_namespace(
                request.app.state.db_engine,
                slug=str(payload.get("slug") or ""),
                display_name=str(payload.get("displayName") or ""),
                description=payload.get("description"),
                actor_user_id=str(user["userId"]),
                platform_roles=[str(role) for role in user.get("platformRoles", [])],
            )
        )
    except NamespaceMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


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


@router.get("/api/v1/namespaces/{slug}/members")
@router.get("/api/web/namespaces/{slug}/members")
async def list_namespace_members_route(
    request: Request,
    slug: str,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "namespace_member_reader", None)
    normalized_page = _parse_non_negative_int(page, 0)
    normalized_size = _parse_positive_int(size, 20)
    try:
        data = await _resolve_result(
            reader(slug, user_id, normalized_page, normalized_size)
            if reader is not None
            else list_namespace_members(
                request.app.state.db_engine,
                slug=slug,
                user_id=user_id,
                page=normalized_page,
                size=normalized_size,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/namespaces/{slug}/member-candidates")
@router.get("/api/web/namespaces/{slug}/member-candidates")
async def search_namespace_member_candidates_route(
    request: Request,
    slug: str,
    search: str = "",
    size: int = 10,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    reader = getattr(request.app.state, "namespace_member_candidate_reader", None)
    normalized_size = _parse_candidate_size(size)
    try:
        data = await _resolve_result(
            reader(slug, search, user_id, normalized_size)
            if reader is not None
            else search_namespace_member_candidates(
                request.app.state.db_engine,
                slug=slug,
                search=search,
                user_id=user_id,
                size=normalized_size,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.post("/api/v1/namespaces/{slug}/members")
@router.post("/api/web/namespaces/{slug}/members")
async def add_namespace_member_route(
    request: Request,
    slug: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_member_add_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, payload["userId"], payload["role"], user_id)
            if writer is not None
            else add_namespace_member(
                request.app.state.db_engine,
                slug=slug,
                member_user_id=str(payload["userId"]),
                role=str(payload["role"]),
                operator_user_id=user_id,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.post("/api/v1/namespaces/{slug}/members/batch")
@router.post("/api/web/namespaces/{slug}/members/batch")
async def batch_add_namespace_members_route(
    request: Request,
    slug: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    members = list(payload.get("members") or [])
    writer = getattr(request.app.state, "namespace_member_batch_add_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, members, user_id)
            if writer is not None
            else batch_add_namespace_members(
                request.app.state.db_engine,
                slug=slug,
                members=members,
                operator_user_id=user_id,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.delete("/api/v1/namespaces/{slug}/members/{member_user_id}")
@router.delete("/api/web/namespaces/{slug}/members/{member_user_id}")
async def remove_namespace_member_route(
    request: Request,
    slug: str,
    member_user_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_member_remove_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, member_user_id, user_id)
            if writer is not None
            else remove_namespace_member(
                request.app.state.db_engine,
                slug=slug,
                member_user_id=member_user_id,
                operator_user_id=user_id,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)


@router.put("/api/v1/namespaces/{slug}/members/{member_user_id}/role")
@router.put("/api/web/namespaces/{slug}/members/{member_user_id}/role")
async def update_namespace_member_role_route(
    request: Request,
    slug: str,
    member_user_id: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_member_update_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, member_user_id, payload["role"], user_id)
            if writer is not None
            else update_namespace_member_role(
                request.app.state.db_engine,
                slug=slug,
                member_user_id=member_user_id,
                role=str(payload["role"]),
                operator_user_id=user_id,
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.put("/api/v1/namespaces/{slug}")
@router.put("/api/web/namespaces/{slug}")
async def update_namespace_route(
    request: Request,
    slug: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _require_current_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_update_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, payload, user)
            if writer is not None
            else update_namespace(
                request.app.state.db_engine,
                slug=slug,
                display_name=payload.get("displayName"),
                description=payload.get("description"),
                actor_user_id=str(user["userId"]),
            )
        )
    except NamespaceMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/namespaces/{slug}")
@router.delete("/api/web/namespaces/{slug}")
async def delete_namespace_route(
    request: Request,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _require_current_user(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_delete_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, user)
            if writer is not None
            else delete_namespace(request.app.state.db_engine, slug=slug, actor_user_id=str(user["userId"]))
        )
    except NamespaceMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)


async def _lifecycle_route(
    *,
    action: str,
    request: Request,
    slug: str,
    payload: dict[str, Any] | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user = await _require_current_user(request, mock_user_id)
    writer = getattr(request.app.state, "namespace_lifecycle_writer", None)
    if writer is not None:
        data = await _resolve_result(writer(action, slug, payload or {}, user, request))
        return ok("\u66f4\u65b0\u6210\u529f", data, request)
    kwargs = {
        "slug": slug,
        "actor_user_id": str(user["userId"]),
        "request_id": request.state.request_id,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    try:
        if action == "freeze":
            data = await freeze_namespace(request.app.state.db_engine, reason=(payload or {}).get("reason"), **kwargs)
        elif action == "unfreeze":
            data = await unfreeze_namespace(request.app.state.db_engine, **kwargs)
        elif action == "archive":
            data = await archive_namespace(request.app.state.db_engine, reason=(payload or {}).get("reason"), **kwargs)
        elif action == "restore":
            data = await restore_namespace(request.app.state.db_engine, **kwargs)
        else:
            raise AssertionError(f"unknown namespace lifecycle action {action}")
    except NamespaceMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/namespaces/{slug}/freeze")
@router.post("/api/web/namespaces/{slug}/freeze")
async def freeze_namespace_route(
    request: Request,
    slug: str,
    payload: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await _lifecycle_route(action="freeze", request=request, slug=slug, payload=payload, mock_user_id=x_mock_user_id)


@router.post("/api/v1/namespaces/{slug}/unfreeze")
@router.post("/api/web/namespaces/{slug}/unfreeze")
async def unfreeze_namespace_route(
    request: Request,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await _lifecycle_route(action="unfreeze", request=request, slug=slug, payload=None, mock_user_id=x_mock_user_id)


@router.post("/api/v1/namespaces/{slug}/archive")
@router.post("/api/web/namespaces/{slug}/archive")
async def archive_namespace_route(
    request: Request,
    slug: str,
    payload: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await _lifecycle_route(action="archive", request=request, slug=slug, payload=payload, mock_user_id=x_mock_user_id)


@router.post("/api/v1/namespaces/{slug}/restore")
@router.post("/api/web/namespaces/{slug}/restore")
async def restore_namespace_route(
    request: Request,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await _lifecycle_route(action="restore", request=request, slug=slug, payload=None, mock_user_id=x_mock_user_id)


@router.post("/api/v1/namespaces/{slug}/transfer-ownership")
@router.post("/api/web/namespaces/{slug}/transfer-ownership")
async def transfer_namespace_ownership_route(
    request: Request,
    slug: str,
    payload: dict[str, Any],
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _require_user_id(request, x_mock_user_id)
    writer = getattr(request.app.state, "namespace_transfer_ownership_writer", None)
    try:
        data = await _resolve_result(
            writer(slug, user_id, payload["newOwnerId"])
            if writer is not None
            else transfer_namespace_ownership(
                request.app.state.db_engine,
                slug=slug,
                current_owner_id=user_id,
                new_owner_id=str(payload["newOwnerId"]),
            )
        )
    except NamespaceMemberReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


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
