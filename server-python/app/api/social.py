from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.social.star import SkillStarError, SkillStarInput, check_skill_star, star_skill


router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _read_optional_user_id(request: Request, mock_user_id: str | None) -> str | None:
    if mock_user_id is None or mock_user_id.strip() == "":
        return None

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        return None
    return str(data["userId"])


async def _require_user_id(request: Request, mock_user_id: str | None) -> str:
    user_id = await _read_optional_user_id(request, mock_user_id)
    if user_id is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return user_id


def _star_input(skill_id: int, user_id: str) -> SkillStarInput:
    return SkillStarInput(skill_id=skill_id, user_id=user_id)


async def star_skill_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    writer = getattr(request.app.state, "skill_star_writer", None)
    try:
        await _resolve_result(
            writer(_star_input(skill_id, user_id))
            if writer is not None
            else star_skill(request.app.state.db_engine, _star_input(skill_id, user_id))
        )
    except SkillStarError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


async def check_skill_star_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "skill_star_reader", None)
    try:
        data = await _resolve_result(
            reader(skill_id, user_id)
            if reader is not None
            else check_skill_star(request.app.state.db_engine, skill_id, user_id)
        )
    except SkillStarError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", bool(data), request)


@router.put("/api/v1/skills/{skill_id}/star")
@router.put("/api/web/skills/{skill_id}/star")
async def star_skill_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await star_skill_route_data(request, skill_id, x_mock_user_id)


@router.get("/api/v1/skills/{skill_id}/star")
@router.get("/api/web/skills/{skill_id}/star")
async def check_skill_star_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await check_skill_star_route_data(request, skill_id, x_mock_user_id)
