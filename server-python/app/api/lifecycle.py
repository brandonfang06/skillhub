from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.response import ok
from app.lifecycle.skill import (
    SkillArchiveInput,
    SkillLifecycleError,
    archive_skill as archive_skill_workflow,
    unarchive_skill as unarchive_skill_workflow,
)


router = APIRouter()


class SkillArchiveRequest(BaseModel):
    reason: str | None = None


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _require_mock_user(mock_user_id: str | None) -> str:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return mock_user_id.strip()


def _build_input(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillArchiveRequest | None,
    user_id: str,
) -> SkillArchiveInput:
    return SkillArchiveInput(
        namespace=namespace,
        slug=slug,
        user_id=user_id,
        reason=body.reason if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


async def archive_skill_route_data(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillArchiveRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    archive_input = _build_input(request, namespace, slug, body, user_id)
    writer = getattr(request.app.state, "skill_archive_writer", None)
    try:
        data = await _resolve_result(
            writer(archive_input) if writer is not None else archive_skill_workflow(request.app.state.db_engine, archive_input)
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def unarchive_skill_route_data(
    request: Request,
    namespace: str,
    slug: str,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    archive_input = _build_input(request, namespace, slug, None, user_id)
    writer = getattr(request.app.state, "skill_unarchive_writer", None)
    try:
        data = await _resolve_result(
            writer(archive_input) if writer is not None else unarchive_skill_workflow(request.app.state.db_engine, archive_input)
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/skills/{namespace}/{slug}/archive")
async def archive_skill_v1(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillArchiveRequest | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await archive_skill_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/archive")
async def archive_skill_web(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillArchiveRequest | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await archive_skill_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/v1/skills/{namespace}/{slug}/unarchive")
async def unarchive_skill_v1(
    request: Request,
    namespace: str,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await unarchive_skill_route_data(request, namespace, slug, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/unarchive")
async def unarchive_skill_web(
    request: Request,
    namespace: str,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await unarchive_skill_route_data(request, namespace, slug, x_mock_user_id)
