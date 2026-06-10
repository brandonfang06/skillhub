from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.social.owned import list_my_owned_skills
from app.social.lists import SocialListKind, list_my_social_skills
from app.social.rating import SkillRatingError, SkillRatingInput, check_skill_rating, rate_skill
from app.social.star import SkillStarError, SkillStarInput, check_skill_star, star_skill, unstar_skill
from app.social.subscription import (
    SkillSubscriptionError,
    SkillSubscriptionInput,
    check_skill_subscription,
    subscribe_skill,
    unsubscribe_skill,
)


router = APIRouter()


class SkillRatingRequest(BaseModel):
    score: int


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


async def _require_user_context(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


def _star_input(skill_id: int, user_id: str) -> SkillStarInput:
    return SkillStarInput(skill_id=skill_id, user_id=user_id)


def _subscription_input(skill_id: int, user_id: str) -> SkillSubscriptionInput:
    return SkillSubscriptionInput(skill_id=skill_id, user_id=user_id)


def _rating_input(skill_id: int, user_id: str, score: int) -> SkillRatingInput:
    return SkillRatingInput(skill_id=skill_id, user_id=user_id, score=score)


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


async def unstar_skill_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    writer = getattr(request.app.state, "skill_unstar_writer", None)
    try:
        await _resolve_result(
            writer(_star_input(skill_id, user_id))
            if writer is not None
            else unstar_skill(request.app.state.db_engine, _star_input(skill_id, user_id))
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


async def subscribe_skill_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    writer = getattr(request.app.state, "skill_subscription_writer", None)
    try:
        await _resolve_result(
            writer(_subscription_input(skill_id, user_id))
            if writer is not None
            else subscribe_skill(request.app.state.db_engine, _subscription_input(skill_id, user_id))
        )
    except SkillSubscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


async def unsubscribe_skill_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    writer = getattr(request.app.state, "skill_unsubscribe_writer", None)
    try:
        await _resolve_result(
            writer(_subscription_input(skill_id, user_id))
            if writer is not None
            else unsubscribe_skill(request.app.state.db_engine, _subscription_input(skill_id, user_id))
        )
    except SkillSubscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


async def check_skill_subscription_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _read_optional_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "skill_subscription_reader", None)
    try:
        data = await _resolve_result(
            reader(skill_id, user_id)
            if reader is not None
            else check_skill_subscription(request.app.state.db_engine, skill_id, user_id)
        )
    except SkillSubscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", bool(data), request)


async def rate_skill_route_data(
    request: Request,
    skill_id: int,
    payload: SkillRatingRequest,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    writer = getattr(request.app.state, "skill_rating_writer", None)
    try:
        await _resolve_result(
            writer(_rating_input(skill_id, user_id, payload.score))
            if writer is not None
            else rate_skill(request.app.state.db_engine, _rating_input(skill_id, user_id, payload.score))
        )
    except SkillRatingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


async def check_skill_rating_route_data(request: Request, skill_id: int, mock_user_id: str | None) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "skill_rating_reader", None)
    try:
        data = await _resolve_result(
            reader(skill_id, user_id)
            if reader is not None
            else check_skill_rating(request.app.state.db_engine, skill_id, user_id)
        )
    except SkillRatingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


def _parse_non_negative_int(value: int, default: int) -> int:
    return value if value >= 0 else default


def _parse_positive_int(value: int, default: int) -> int:
    return value if value > 0 else default


async def list_my_social_skills_route_data(
    request: Request,
    *,
    kind: SocialListKind,
    mock_user_id: str | None,
    page: int,
    size: int,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    normalized_page = _parse_non_negative_int(page, 0)
    normalized_size = _parse_positive_int(size, 12)
    reader = getattr(request.app.state, "my_social_list_reader", None)
    data = await _resolve_result(
        reader(kind, user_id, normalized_page, normalized_size)
        if reader is not None
        else list_my_social_skills(
            request.app.state.db_engine,
            kind=kind,
            user_id=user_id,
            page=normalized_page,
            size=normalized_size,
        )
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def list_my_owned_skills_route_data(
    request: Request,
    *,
    mock_user_id: str | None,
    page: int,
    size: int,
    filter_value: str | None,
    keyword: str | None,
    namespace: str | None,
) -> dict[str, Any]:
    user = await _require_user_context(request, mock_user_id)
    user_id = str(user["userId"])
    platform_roles = {str(role) for role in user.get("platformRoles", [])}
    normalized_page = _parse_non_negative_int(page, 0)
    normalized_size = _parse_positive_int(size, 10)
    reader = getattr(request.app.state, "my_skills_reader", None)
    data = await _resolve_result(
        reader(user_id, platform_roles, normalized_page, normalized_size, filter_value, keyword, namespace)
        if reader is not None
        else list_my_owned_skills(
            request.app.state.db_engine,
            user_id=user_id,
            platform_roles=platform_roles,
            page=normalized_page,
            size=normalized_size,
            filter_value=filter_value,
            keyword=keyword,
            namespace=namespace,
        )
    )
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/me/skills")
@router.get("/api/web/me/skills")
async def list_my_skills_route(
    request: Request,
    page: int = 0,
    size: int = 10,
    filter: str | None = None,
    q: str | None = None,
    namespace: str | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_my_owned_skills_route_data(
        request,
        mock_user_id=x_mock_user_id,
        page=page,
        size=size,
        filter_value=filter,
        keyword=q,
        namespace=namespace,
    )


@router.get("/api/v1/me/stars")
@router.get("/api/web/me/stars")
async def list_my_stars_route(
    request: Request,
    page: int = 0,
    size: int = 12,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_my_social_skills_route_data(
        request,
        kind="stars",
        mock_user_id=x_mock_user_id,
        page=page,
        size=size,
    )


@router.get("/api/v1/me/subscriptions")
@router.get("/api/web/me/subscriptions")
async def list_my_subscriptions_route(
    request: Request,
    page: int = 0,
    size: int = 12,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_my_social_skills_route_data(
        request,
        kind="subscriptions",
        mock_user_id=x_mock_user_id,
        page=page,
        size=size,
    )


@router.put("/api/v1/skills/{skill_id}/star")
@router.put("/api/web/skills/{skill_id}/star")
async def star_skill_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await star_skill_route_data(request, skill_id, x_mock_user_id)


@router.delete("/api/v1/skills/{skill_id}/star")
@router.delete("/api/web/skills/{skill_id}/star")
async def unstar_skill_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await unstar_skill_route_data(request, skill_id, x_mock_user_id)


@router.get("/api/v1/skills/{skill_id}/star")
@router.get("/api/web/skills/{skill_id}/star")
async def check_skill_star_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await check_skill_star_route_data(request, skill_id, x_mock_user_id)


@router.put("/api/v1/skills/{skill_id}/subscription")
@router.put("/api/web/skills/{skill_id}/subscription")
async def subscribe_skill_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await subscribe_skill_route_data(request, skill_id, x_mock_user_id)


@router.delete("/api/v1/skills/{skill_id}/subscription")
@router.delete("/api/web/skills/{skill_id}/subscription")
async def unsubscribe_skill_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await unsubscribe_skill_route_data(request, skill_id, x_mock_user_id)


@router.get("/api/v1/skills/{skill_id}/subscription")
@router.get("/api/web/skills/{skill_id}/subscription")
async def check_skill_subscription_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await check_skill_subscription_route_data(request, skill_id, x_mock_user_id)


@router.put("/api/v1/skills/{skill_id}/rating")
@router.put("/api/web/skills/{skill_id}/rating")
async def rate_skill_route(
    request: Request,
    skill_id: int,
    payload: SkillRatingRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await rate_skill_route_data(request, skill_id, payload, x_mock_user_id)


@router.get("/api/v1/skills/{skill_id}/rating")
@router.get("/api/web/skills/{skill_id}/rating")
async def check_skill_rating_route(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await check_skill_rating_route_data(request, skill_id, x_mock_user_id)
