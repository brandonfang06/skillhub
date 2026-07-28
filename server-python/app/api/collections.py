from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.auth.context import resolve_current_user_or_401
from app.auth.policy import (
    platform_roles,
    reject_api_token_principal_for_route,
)
from app.collections.access import CollectionAccessError
from app.collections.contracts import (
    CollectionCreateRequest,
    CollectionDeletedEnvelope,
    CollectionDetailEnvelope,
    CollectionDraftReplaceRequest,
    CollectionListEnvelope,
    CollectionPublishRequest,
    CollectionResolveEnvelope,
    CollectionStatusRequest,
    CollectionVersionEnvelope,
)
from app.collections.read_repository import (
    CollectionReadError,
    get_collection as read_collection_detail,
    list_collections,
    resolve_collection,
)
from app.collections.service import (
    CollectionMutationError,
    MutationContext,
    create_collection,
    create_collection_draft,
    delete_collection_draft,
    publish_collection,
    replace_collection_draft,
    set_collection_status,
)
from app.core.config import get_settings
from app.core.response import ok
from app.skills.read_repository import optional_current_user


def _require_collections_enabled(request: Request) -> None:
    settings = getattr(request.app.state, "settings", None)
    enabled = (
        bool(getattr(settings, "collections_enabled", False))
        if settings is not None
        else get_settings().collections_enabled
    )
    if not enabled:
        raise HTTPException(status_code=404, detail="error.collection.notFound")


router = APIRouter(dependencies=[Depends(_require_collections_enabled)])


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _raise_collection_http(exc: Exception) -> None:
    status_code = int(getattr(exc, "status_code", 400))
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


async def _read_identity(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> tuple[str | None, list[str]]:
    user = await optional_current_user(request, mock_user_id, authorization)
    if user is None:
        return None, []
    return str(user["userId"]), platform_roles(user)


async def _current_web_user(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = dict(
        await resolve_current_user_or_401(
            request,
            mock_user_id,
            authorization,
        )
    )
    reject_api_token_principal_for_route(user, request.url.path)
    return user


def _mutation_context(request: Request, user: dict[str, Any]) -> MutationContext:
    return MutationContext(
        actor_user_id=str(user["userId"]),
        platform_roles=platform_roles(user),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _parse_if_match(value: str | None) -> int:
    if value is None:
        raise CollectionMutationError("error.collection.draft.ifMatch.required")
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:].strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        normalized = normalized[1:-1]
    if not normalized.isdigit() or int(normalized) <= 0:
        raise CollectionMutationError("error.collection.draft.ifMatch.required")
    return int(normalized)


async def _read_after_mutation(
    request: Request,
    *,
    namespace: str,
    collection: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    return await read_collection_detail(
        request.app.state.db_engine,
        namespace=namespace,
        collection=collection,
        current_user_id=str(user["userId"]),
        platform_roles=platform_roles(user),
    )


async def _injected_mutation(
    request: Request,
    *,
    action: str,
    namespace: str,
    collection: str | None,
    payload: object,
    idempotency_key: str | None,
    expected_revision: int | None,
    user: dict[str, Any],
) -> Any | None:
    writer = getattr(request.app.state, "collection_mutation_writer", None)
    if writer is None:
        return None
    return await _resolve_result(
        writer(
            action,
            namespace,
            collection,
            payload,
            idempotency_key,
            expected_revision,
            user,
            request,
        )
    )


@router.get(
    "/api/web/namespaces/{namespace}/collections",
    response_model=CollectionListEnvelope,
)
async def list_collections_route(
    request: Request,
    namespace: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    current_user_id, roles = await _read_identity(request, x_mock_user_id, authorization)
    reader = getattr(request.app.state, "collection_reader", None)
    try:
        data = await _resolve_result(
            reader("list", namespace, None, current_user_id, roles)
            if reader is not None
            else list_collections(
                request.app.state.db_engine,
                namespace=namespace,
                current_user_id=current_user_id,
                platform_roles=roles,
            )
        )
    except (CollectionReadError, CollectionAccessError) as exc:
        _raise_collection_http(exc)
    return ok("collection.list.found", data, request)


@router.get(
    "/api/web/collections/{namespace}/{collection}",
    response_model=CollectionDetailEnvelope,
)
async def get_collection_route(
    request: Request,
    namespace: str,
    collection: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    current_user_id, roles = await _read_identity(request, x_mock_user_id, authorization)
    reader = getattr(request.app.state, "collection_reader", None)
    try:
        data = await _resolve_result(
            reader("detail", namespace, collection, current_user_id, roles)
            if reader is not None
            else read_collection_detail(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                current_user_id=current_user_id,
                platform_roles=roles,
            )
        )
    except (CollectionReadError, CollectionAccessError) as exc:
        _raise_collection_http(exc)
    return ok("collection.found", data, request)


@router.get(
    "/api/cli/v1/collections/{namespace}/{collection}/resolve",
    response_model=CollectionResolveEnvelope,
)
async def resolve_collection_route(
    request: Request,
    namespace: str,
    collection: str,
    version: str | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    current_user_id, roles = await _read_identity(request, x_mock_user_id, authorization)
    reader = getattr(request.app.state, "collection_resolver", None)
    try:
        data = await _resolve_result(
            reader(namespace, collection, version, current_user_id, roles)
            if reader is not None
            else resolve_collection(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                version=version,
                current_user_id=current_user_id,
                platform_roles=roles,
            )
        )
    except (CollectionReadError, CollectionAccessError) as exc:
        _raise_collection_http(exc)
    return ok("collection.resolve.found", data, request)


@router.post(
    "/api/web/namespaces/{namespace}/collections",
    response_model=CollectionDetailEnvelope,
)
async def create_collection_route(
    request: Request,
    namespace: str,
    payload: CollectionCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        injected = await _injected_mutation(
            request,
            action="create",
            namespace=namespace,
            collection=None,
            payload=payload,
            idempotency_key=idempotency_key,
            expected_revision=None,
            user=user,
        )
        if injected is not None:
            data = injected
        else:
            await create_collection(
                request.app.state.db_engine,
                namespace=namespace,
                slug=payload.slug,
                display_name=payload.display_name,
                summary=payload.summary,
                idempotency_key=idempotency_key,
                context=_mutation_context(request, user),
            )
            data = await _read_after_mutation(
                request,
                namespace=namespace,
                collection=payload.slug,
                user=user,
            )
    except (CollectionMutationError, CollectionAccessError, CollectionReadError) as exc:
        _raise_collection_http(exc)
    return ok("collection.created", data, request)


@router.post(
    "/api/web/collections/{namespace}/{collection}/draft",
    response_model=CollectionVersionEnvelope,
)
async def create_collection_draft_route(
    request: Request,
    namespace: str,
    collection: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        injected = await _injected_mutation(
            request,
            action="create_draft",
            namespace=namespace,
            collection=collection,
            payload=None,
            idempotency_key=None,
            expected_revision=None,
            user=user,
        )
        if injected is not None:
            data = injected
        else:
            await create_collection_draft(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                context=_mutation_context(request, user),
            )
            detail = await _read_after_mutation(
                request,
                namespace=namespace,
                collection=collection,
                user=user,
            )
            data = detail["draft"]
    except (CollectionMutationError, CollectionAccessError, CollectionReadError) as exc:
        _raise_collection_http(exc)
    return ok("collection.draft.created", data, request)


@router.put(
    "/api/web/collections/{namespace}/{collection}/draft",
    response_model=CollectionVersionEnvelope,
)
async def replace_collection_draft_route(
    request: Request,
    namespace: str,
    collection: str,
    payload: CollectionDraftReplaceRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        expected_revision = _parse_if_match(if_match)
        injected = await _injected_mutation(
            request,
            action="replace_draft",
            namespace=namespace,
            collection=collection,
            payload=payload,
            idempotency_key=None,
            expected_revision=expected_revision,
            user=user,
        )
        if injected is not None:
            data = injected
        else:
            await replace_collection_draft(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                payload=payload,
                expected_revision=expected_revision,
                context=_mutation_context(request, user),
            )
            detail = await _read_after_mutation(
                request,
                namespace=namespace,
                collection=collection,
                user=user,
            )
            data = detail["draft"]
    except (CollectionMutationError, CollectionAccessError, CollectionReadError) as exc:
        _raise_collection_http(exc)
    return ok("collection.draft.updated", data, request)


@router.delete(
    "/api/web/collections/{namespace}/{collection}/draft",
    response_model=CollectionDeletedEnvelope,
)
async def delete_collection_draft_route(
    request: Request,
    namespace: str,
    collection: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        injected = await _injected_mutation(
            request,
            action="delete_draft",
            namespace=namespace,
            collection=collection,
            payload=None,
            idempotency_key=None,
            expected_revision=None,
            user=user,
        )
        data = (
            injected
            if injected is not None
            else await delete_collection_draft(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                context=_mutation_context(request, user),
            )
        )
    except (CollectionMutationError, CollectionAccessError) as exc:
        _raise_collection_http(exc)
    return ok("collection.draft.deleted", data, request)


@router.post(
    "/api/web/collections/{namespace}/{collection}/publish",
    response_model=CollectionVersionEnvelope,
)
async def publish_collection_route(
    request: Request,
    namespace: str,
    collection: str,
    payload: CollectionPublishRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        injected = await _injected_mutation(
            request,
            action="publish",
            namespace=namespace,
            collection=collection,
            payload=payload,
            idempotency_key=idempotency_key,
            expected_revision=None,
            user=user,
        )
        if injected is not None:
            data = injected
        else:
            await publish_collection(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                payload=payload,
                idempotency_key=idempotency_key,
                context=_mutation_context(request, user),
            )
            detail = await _read_after_mutation(
                request,
                namespace=namespace,
                collection=collection,
                user=user,
            )
            data = detail["latestPublishedVersion"]
    except (CollectionMutationError, CollectionAccessError, CollectionReadError) as exc:
        _raise_collection_http(exc)
    return ok("collection.published", data, request)


@router.put(
    "/api/web/collections/{namespace}/{collection}/status",
    response_model=CollectionDetailEnvelope,
)
async def set_collection_status_route(
    request: Request,
    namespace: str,
    collection: str,
    payload: CollectionStatusRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        injected = await _injected_mutation(
            request,
            action="status",
            namespace=namespace,
            collection=collection,
            payload=payload,
            idempotency_key=None,
            expected_revision=None,
            user=user,
        )
        if injected is not None:
            data = injected
        else:
            await set_collection_status(
                request.app.state.db_engine,
                namespace=namespace,
                collection=collection,
                payload=payload,
                context=_mutation_context(request, user),
            )
            data = await _read_after_mutation(
                request,
                namespace=namespace,
                collection=collection,
                user=user,
            )
    except (CollectionMutationError, CollectionAccessError, CollectionReadError) as exc:
        _raise_collection_http(exc)
    return ok("collection.status.updated", data, request)
