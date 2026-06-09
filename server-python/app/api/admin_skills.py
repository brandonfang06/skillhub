from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.admin.skill import (
    AdminSkillGovernanceError,
    AdminSkillGovernanceInput,
    hide_skill_as_admin,
    unhide_skill_as_admin,
    yank_skill_version_as_admin,
)
from app.api.auth import read_current_mock_user
from app.core.response import ok


router = APIRouter()


class AdminSkillActionRequest(BaseModel):
    reason: str | None = None


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, object]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


def _require_super_admin(user: dict[str, object]) -> str:
    roles = {str(role) for role in user.get("platformRoles", [])}
    if "SUPER_ADMIN" not in roles:
        raise HTTPException(status_code=403, detail="error.admin.superAdminRequired")
    return str(user["userId"])


def _require_skill_admin_or_super_admin(user: dict[str, object]) -> str:
    roles = {str(role) for role in user.get("platformRoles", [])}
    if roles.isdisjoint({"SKILL_ADMIN", "SUPER_ADMIN"}):
        raise HTTPException(status_code=403, detail="error.admin.skillAdminRequired")
    return str(user["userId"])


def _build_input(
    request: Request,
    skill_id: int,
    actor_user_id: str,
    body: AdminSkillActionRequest | None,
) -> AdminSkillGovernanceInput:
    return AdminSkillGovernanceInput(
        skill_id=skill_id,
        actor_user_id=actor_user_id,
        reason=body.reason if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


async def hide_skill_route_data(
    request: Request,
    skill_id: int,
    body: AdminSkillActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    actor_user_id = _require_super_admin(await _read_current_user(request, mock_user_id))
    governance_input = _build_input(request, skill_id, actor_user_id, body)
    writer = getattr(request.app.state, "admin_skill_hide_writer", None)
    try:
        data = await _resolve_result(
            writer(governance_input)
            if writer is not None
            else hide_skill_as_admin(request.app.state.db_engine, governance_input)
        )
    except AdminSkillGovernanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def unhide_skill_route_data(
    request: Request,
    skill_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    actor_user_id = _require_super_admin(await _read_current_user(request, mock_user_id))
    governance_input = _build_input(request, skill_id, actor_user_id, None)
    writer = getattr(request.app.state, "admin_skill_unhide_writer", None)
    try:
        data = await _resolve_result(
            writer(governance_input)
            if writer is not None
            else unhide_skill_as_admin(request.app.state.db_engine, governance_input)
        )
    except AdminSkillGovernanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def yank_skill_version_route_data(
    request: Request,
    version_id: int,
    body: AdminSkillActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    actor_user_id = _require_skill_admin_or_super_admin(await _read_current_user(request, mock_user_id))
    governance_input = _build_input(request, version_id, actor_user_id, body)
    writer = getattr(request.app.state, "admin_skill_version_yank_writer", None)
    try:
        data = await _resolve_result(
            writer(governance_input)
            if writer is not None
            else yank_skill_version_as_admin(request.app.state.db_engine, governance_input)
        )
    except AdminSkillGovernanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/admin/skills/{skill_id}/hide")
async def hide_skill(
    request: Request,
    skill_id: int,
    body: AdminSkillActionRequest | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await hide_skill_route_data(request, skill_id, body, x_mock_user_id)


@router.post("/api/v1/admin/skills/{skill_id}/unhide")
async def unhide_skill(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await unhide_skill_route_data(request, skill_id, x_mock_user_id)


@router.post("/api/v1/admin/skills/versions/{version_id}/yank")
async def yank_skill_version(
    request: Request,
    version_id: int,
    body: AdminSkillActionRequest | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await yank_skill_version_route_data(request, version_id, body, x_mock_user_id)
