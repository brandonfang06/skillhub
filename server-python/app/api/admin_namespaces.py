from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.admin_namespace import mutations as admin_mutations
from app.admin_namespace.contracts import (
    AdminNamespaceBatchMemberEnvelope,
    AdminNamespaceBatchMemberRequest,
    AdminNamespaceCandidateListEnvelope,
    AdminNamespaceDetailEnvelope,
    AdminNamespaceLifecycleRequest,
    AdminNamespaceListEnvelope,
    AdminNamespaceMemberEnvelope,
    AdminNamespaceMemberPageEnvelope,
    AdminNamespaceMemberRequest,
    AdminNamespaceMessageEnvelope,
    AdminNamespaceTransferOwnershipRequest,
    AdminNamespaceUpdateMemberRoleRequest,
)
from app.admin_namespace.mutation_repository import AdminNamespaceMutationError
from app.admin_namespace.read_repository import (
    AdminNamespaceReadError,
    get_admin_namespace,
    list_admin_namespace_members,
    list_admin_namespaces,
    normalize_candidate_size,
    normalize_page,
    normalize_page_size,
    search_admin_namespace_member_candidates,
)
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import require_platform_role
from app.core.response import ok

router = APIRouter(tags=["Admin Namespaces"])


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    return await result if isawaitable(result) else result


async def _require_super_admin(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(
        request,
        mock_user_id,
        authorization,
    )
    user = dict(
        await resolve_current_user_or_401(
            request,
            mock_user_id,
            authorization,
        )
    )
    require_platform_role(
        user,
        "SUPER_ADMIN",
        detail="error.admin.superAdminRequired",
    )
    return user


@router.get(
    "/api/v1/admin/namespaces",
    response_model=AdminNamespaceListEnvelope,
)
async def list_admin_namespaces_route(
    request: Request,
    keyword: str | None = None,
    status: str | None = None,
    type: str | None = None,
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    reader = getattr(request.app.state, "admin_namespace_list_reader", None)
    try:
        normalized_page = normalize_page(page)
        normalized_size = normalize_page_size(size)
        data = await _resolve_result(
            reader(
                keyword=keyword,
                status=status,
                namespace_type=type,
                page=normalized_page,
                size=normalized_size,
                actor_user_id=str(user["userId"]),
            )
            if reader is not None
            else list_admin_namespaces(
                request.app.state.db_engine,
                keyword=keyword,
                status=status,
                namespace_type=type,
                page=normalized_page,
                size=normalized_size,
                actor_user_id=str(user["userId"]),
            )
        )
    except AdminNamespaceReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.get(
    "/api/v1/admin/namespaces/{slug}",
    response_model=AdminNamespaceDetailEnvelope,
)
async def get_admin_namespace_route(
    request: Request,
    slug: str,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    reader = getattr(request.app.state, "admin_namespace_detail_reader", None)
    try:
        data = await _resolve_result(
            reader(slug=slug, actor_user_id=str(user["userId"]))
            if reader is not None
            else get_admin_namespace(
                request.app.state.db_engine,
                slug=slug,
                actor_user_id=str(user["userId"]),
            )
        )
    except AdminNamespaceReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.get(
    "/api/v1/admin/namespaces/{slug}/members",
    response_model=AdminNamespaceMemberPageEnvelope,
)
async def list_admin_namespace_members_route(
    request: Request,
    slug: str,
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await _require_super_admin(request, mock_user_id, authorization)
    reader = getattr(request.app.state, "admin_namespace_member_reader", None)
    try:
        normalized_page = normalize_page(page)
        normalized_size = normalize_page_size(size)
        data = await _resolve_result(
            reader(slug=slug, page=normalized_page, size=normalized_size)
            if reader is not None
            else list_admin_namespace_members(
                request.app.state.db_engine,
                slug=slug,
                page=normalized_page,
                size=normalized_size,
            )
        )
    except AdminNamespaceReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.get(
    "/api/v1/admin/namespaces/{slug}/member-candidates",
    response_model=AdminNamespaceCandidateListEnvelope,
)
async def search_admin_namespace_member_candidates_route(
    request: Request,
    slug: str,
    search: str,
    size: int = 10,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await _require_super_admin(request, mock_user_id, authorization)
    normalized_size = normalize_candidate_size(size)
    reader = getattr(request.app.state, "admin_namespace_candidate_reader", None)
    try:
        data = await _resolve_result(
            reader(slug=slug, search=search, size=normalized_size)
            if reader is not None
            else search_admin_namespace_member_candidates(
                request.app.state.db_engine,
                slug=slug,
                search=search,
                size=normalized_size,
            )
        )
    except AdminNamespaceReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


def _request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.state.request_id,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


async def _mutation_call(
    request: Request,
    method: str,
    **kwargs: Any,
) -> Any:
    writer = getattr(request.app.state, "admin_namespace_mutation_writer", None)
    try:
        if writer is not None:
            return await _resolve_result(getattr(writer, method)(**kwargs))
        return await getattr(admin_mutations, method)(
            request.app.state.db_engine, **kwargs
        )
    except AdminNamespaceMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/api/v1/admin/namespaces/{slug}/members",
    response_model=AdminNamespaceMemberEnvelope,
)
async def add_admin_namespace_member_route(
    request: Request,
    slug: str,
    payload: AdminNamespaceMemberRequest,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "add_member",
        slug=slug,
        member_user_id=payload.userId,
        role=payload.role,
        actor_user_id=str(user["userId"]),
        **_request_context(request),
    )
    return ok("response.success.created", data, request)


@router.post(
    "/api/v1/admin/namespaces/{slug}/members/batch",
    response_model=AdminNamespaceBatchMemberEnvelope,
)
async def batch_add_admin_namespace_members_route(
    request: Request,
    slug: str,
    payload: AdminNamespaceBatchMemberRequest,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "batch_add_members",
        slug=slug,
        members=[item.model_dump() for item in payload.members],
        actor_user_id=str(user["userId"]),
        **_request_context(request),
    )
    return ok("response.success.created", data, request)


@router.put(
    "/api/v1/admin/namespaces/{slug}/members/{userId}/role",
    response_model=AdminNamespaceMemberEnvelope,
)
async def update_admin_namespace_member_role_route(
    request: Request,
    slug: str,
    userId: str,
    payload: AdminNamespaceUpdateMemberRoleRequest,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "update_member_role",
        slug=slug,
        member_user_id=userId,
        role=payload.role,
        actor_user_id=str(user["userId"]),
        **_request_context(request),
    )
    return ok("response.success.updated", data, request)


@router.delete(
    "/api/v1/admin/namespaces/{slug}/members/{userId}",
    response_model=AdminNamespaceMessageEnvelope,
)
async def remove_admin_namespace_member_route(
    request: Request,
    slug: str,
    userId: str,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "remove_member",
        slug=slug,
        member_user_id=userId,
        actor_user_id=str(user["userId"]),
        **_request_context(request),
    )
    return ok("response.success.deleted", data, request)


@router.post(
    "/api/v1/admin/namespaces/{slug}/transfer-ownership",
    response_model=AdminNamespaceMessageEnvelope,
)
async def transfer_admin_namespace_ownership_route(
    request: Request,
    slug: str,
    payload: AdminNamespaceTransferOwnershipRequest,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "transfer_ownership",
        slug=slug,
        new_owner_id=payload.newOwnerId,
        actor_user_id=str(user["userId"]),
        **_request_context(request),
    )
    return ok("response.success.updated", data, request)


async def _admin_namespace_lifecycle_route(
    *,
    action: str,
    request: Request,
    slug: str,
    payload: AdminNamespaceLifecycleRequest | None,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = await _require_super_admin(request, mock_user_id, authorization)
    data = await _mutation_call(
        request,
        "transition",
        action=action,
        slug=slug,
        actor_user_id=str(user["userId"]),
        reason=payload.reason if payload is not None else None,
        **_request_context(request),
    )
    return ok("response.success.updated", data, request)


@router.post(
    "/api/v1/admin/namespaces/{slug}/freeze",
    response_model=AdminNamespaceDetailEnvelope,
)
async def freeze_admin_namespace_route(
    request: Request,
    slug: str,
    payload: AdminNamespaceLifecycleRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await _admin_namespace_lifecycle_route(
        action="freeze",
        request=request,
        slug=slug,
        payload=payload,
        mock_user_id=mock_user_id,
        authorization=authorization,
    )


@router.post(
    "/api/v1/admin/namespaces/{slug}/unfreeze",
    response_model=AdminNamespaceDetailEnvelope,
)
async def unfreeze_admin_namespace_route(
    request: Request,
    slug: str,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await _admin_namespace_lifecycle_route(
        action="unfreeze",
        request=request,
        slug=slug,
        payload=None,
        mock_user_id=mock_user_id,
        authorization=authorization,
    )


@router.post(
    "/api/v1/admin/namespaces/{slug}/archive",
    response_model=AdminNamespaceDetailEnvelope,
)
async def archive_admin_namespace_route(
    request: Request,
    slug: str,
    payload: AdminNamespaceLifecycleRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await _admin_namespace_lifecycle_route(
        action="archive",
        request=request,
        slug=slug,
        payload=payload,
        mock_user_id=mock_user_id,
        authorization=authorization,
    )


@router.post(
    "/api/v1/admin/namespaces/{slug}/restore",
    response_model=AdminNamespaceDetailEnvelope,
)
async def restore_admin_namespace_route(
    request: Request,
    slug: str,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await _admin_namespace_lifecycle_route(
        action="restore",
        request=request,
        slug=slug,
        payload=None,
        mock_user_id=mock_user_id,
        authorization=authorization,
    )
