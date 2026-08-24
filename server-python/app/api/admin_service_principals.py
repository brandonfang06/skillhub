from __future__ import annotations

from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import platform_roles
from app.core.response import ok
from app.service_accounts.service import (
    ServiceAccountError,
    create_service_principal,
    create_service_token,
    list_service_principals,
    list_service_tokens,
    require_service_account_admin,
    revoke_service_token,
    rotate_service_token,
    update_service_principal,
)

router = APIRouter()


class CreateServicePrincipalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    displayName: str


class UpdateServicePrincipalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str | None = None
    status: Literal["ACTIVE", "DISABLED"] | None = None


class CreateServiceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    scopes: list[str]
    expiresAt: datetime | None


class RotateServiceTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expiresAt: datetime | None


def _instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _principal_data(principal: Any) -> dict[str, Any]:
    return {
        "id": principal.id,
        "code": principal.code,
        "displayName": principal.display_name,
        "status": principal.status,
        "activeTokenCount": int(getattr(principal, "active_token_count", 0)),
        "nearestTokenExpiry": _instant(
            getattr(principal, "nearest_token_expiry", None)
        ),
        "lastUsedAt": _instant(getattr(principal, "last_used_at", None)),
        "createdAt": _instant(principal.created_at),
        "updatedAt": _instant(principal.updated_at),
    }


def _token_data(token: Any, *, include_secret: bool = False) -> dict[str, Any]:
    data = {
        "id": token.id,
        "servicePrincipalId": token.service_principal_id,
        "name": token.name,
        "tokenPrefix": token.token_prefix,
        "scopes": list(token.scopes),
        "createdAt": _instant(token.created_at),
        "expiresAt": _instant(token.expires_at),
        "lastUsedAt": _instant(token.last_used_at),
        "revokedAt": _instant(token.revoked_at),
    }
    if include_secret:
        data["token"] = token.token
    return data


async def _admin(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    try:
        require_service_account_admin(platform_roles(user))
    except ServiceAccountError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return user


async def _invoke(request: Request, operation: str, fallback: Any, **kwargs: Any) -> Any:
    overrides = getattr(request.app.state, "service_principal_admin", {})
    result = overrides.get(operation, fallback)(**kwargs)
    return await result if isawaitable(result) else result


def _raise_service_error(exc: ServiceAccountError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/api/v1/admin/service-principals")
async def list_service_principals_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        items, total = await _invoke(
            request,
            "list",
            list_service_principals,
            engine=getattr(request.app.state, "db_engine", None),
            page=page,
            size=size,
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.servicePrincipal.listed",
        {
            "items": [_principal_data(item) for item in items],
            "total": total,
            "page": page,
            "size": size,
        },
        request,
    )


@router.post("/api/v1/admin/service-principals")
async def create_service_principal_route(
    request: Request,
    body: CreateServicePrincipalRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        principal = await _invoke(
            request,
            "create",
            create_service_principal,
            engine=getattr(request.app.state, "db_engine", None),
            code=body.code,
            display_name=body.displayName,
            actor_user_id=str(user["userId"]),
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.servicePrincipal.created", _principal_data(principal), request
    )


@router.patch("/api/v1/admin/service-principals/{service_principal_id}")
async def update_service_principal_route(
    request: Request,
    body: UpdateServicePrincipalRequest,
    service_principal_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        principal = await _invoke(
            request,
            "update",
            update_service_principal,
            engine=getattr(request.app.state, "db_engine", None),
            service_principal_id=service_principal_id,
            display_name=body.displayName,
            status=body.status,
            actor_user_id=str(user["userId"]),
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.servicePrincipal.updated", _principal_data(principal), request
    )


@router.get("/api/v1/admin/service-principals/{service_principal_id}/tokens")
async def list_service_tokens_route(
    request: Request,
    service_principal_id: str,
    includeRevoked: bool = False,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        tokens = await _invoke(
            request,
            "list_tokens",
            list_service_tokens,
            engine=getattr(request.app.state, "db_engine", None),
            service_principal_id=service_principal_id,
            actor_platform_roles=platform_roles(user),
            include_revoked=includeRevoked,
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.serviceToken.listed",
        {"items": [_token_data(token) for token in tokens]},
        request,
    )


@router.post("/api/v1/admin/service-principals/{service_principal_id}/tokens")
async def create_service_token_route(
    request: Request,
    body: CreateServiceTokenRequest,
    service_principal_id: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        token = await _invoke(
            request,
            "create_token",
            create_service_token,
            engine=getattr(request.app.state, "db_engine", None),
            service_principal_id=service_principal_id,
            name=body.name,
            scopes=body.scopes,
            expires_at=body.expiresAt,
            actor_user_id=str(user["userId"]),
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.serviceToken.created",
        _token_data(token, include_secret=True),
        request,
    )


@router.post(
    "/api/v1/admin/service-principals/{service_principal_id}/tokens/{token_id}/rotate"
)
async def rotate_service_token_route(
    request: Request,
    body: RotateServiceTokenRequest,
    service_principal_id: str,
    token_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        token = await _invoke(
            request,
            "rotate_token",
            rotate_service_token,
            engine=getattr(request.app.state, "db_engine", None),
            service_principal_id=service_principal_id,
            token_id=token_id,
            expires_at=body.expiresAt,
            actor_user_id=str(user["userId"]),
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return ok(
        "response.success.serviceToken.rotated",
        _token_data(token, include_secret=True),
        request,
    )


@router.delete(
    "/api/v1/admin/service-principals/{service_principal_id}/tokens/{token_id}",
    status_code=204,
)
async def revoke_service_token_route(
    request: Request,
    service_principal_id: str,
    token_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    user = await _admin(request, x_mock_user_id, authorization)
    try:
        await _invoke(
            request,
            "revoke_token",
            revoke_service_token,
            engine=getattr(request.app.state, "db_engine", None),
            service_principal_id=service_principal_id,
            token_id=token_id,
            actor_user_id=str(user["userId"]),
            actor_platform_roles=platform_roles(user),
        )
    except ServiceAccountError as exc:
        raise _raise_service_error(exc) from exc
    return Response(status_code=204)
