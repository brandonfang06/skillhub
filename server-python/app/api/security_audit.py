from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import resolve_current_user_or_401
from app.auth.policy import is_api_token_principal, platform_roles, require_api_token_scope
from app.core.response import ok
from app.object_storage import object_storage_for_settings
from app.security_audit import SecurityAuditReadError, list_security_audits
from app.security_scan_retry import SecurityScanRetryError, SecurityScanRetryInput, retry_security_scan


router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    return dict(await resolve_current_user_or_401(request, mock_user_id, None))


def _user_id(user: dict[str, Any]) -> str:
    value = user.get("userId") or user.get("id")
    if value is None or str(value).strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(value)


def _roles(user: dict[str, Any]) -> list[str]:
    return platform_roles(user)


@router.get("/api/v1/skills/{skill_id}/versions/{version_id}/security-audit")
async def get_security_audits_route(
    request: Request,
    skill_id: int,
    version_id: int,
    scannerType: str | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await _read_current_user(request, x_mock_user_id)
    reader = getattr(request.app.state, "security_audit_reader", None)
    try:
        data = await _resolve_result(
            reader(skill_id, version_id, scannerType, user)
            if reader is not None
            else list_security_audits(
                request.app.state.db_engine,
                skill_id=skill_id,
                version_id=version_id,
                scanner_type=scannerType,
                current_user_id=_user_id(user),
                platform_roles=_roles(user),
            )
        )
    except SecurityAuditReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("security_audit.found", data, request)


@router.post("/api/v1/skills/{skill_id}/versions/{version_id}/security-audit/retry")
async def retry_security_audit_route(
    request: Request,
    skill_id: int,
    version_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = dict(await resolve_current_user_or_401(request, x_mock_user_id, authorization))
    if is_api_token_principal(user):
        require_api_token_scope(user, "skill:publish")
    settings = request.app.state.settings
    storage = object_storage_for_settings(settings)
    try:
        data = await retry_security_scan(
            request.app.state.db_engine,
            SecurityScanRetryInput(
                skill_id=skill_id,
                version_id=version_id,
                user_id=_user_id(user),
                platform_roles=set(_roles(user)),
                scanner_enabled=bool(settings.security_scanner_enabled),
                bundle_exists=storage.exists,
                request_id=getattr(request.state, "request_id", None),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            ),
        )
    except SecurityScanRetryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.updated", data, request)
