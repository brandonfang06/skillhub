from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.security_audit import SecurityAuditReadError, list_security_audits


router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


def _user_id(user: dict[str, Any]) -> str:
    value = user.get("userId") or user.get("id")
    if value is None or str(value).strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(value)


def _roles(user: dict[str, Any]) -> list[str]:
    return [str(role) for role in user.get("platformRoles", [])]


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
