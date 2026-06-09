from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.core.response import ok
from app.promotion.query import (
    PromotionListQuery,
    PromotionQueryError,
    list_pending_promotions,
    list_promotions,
    read_promotion_detail,
)
from app.promotion.workflow import (
    PromotionApproveInput,
    PromotionRejectInput,
    PromotionSubmitInput,
    PromotionWorkflowError,
    approve_promotion,
    reject_promotion,
    submit_promotion,
)


router = APIRouter()


class PromotionRequestBody(BaseModel):
    sourceSkillId: int
    sourceVersionId: int
    targetNamespaceId: int


class PromotionActionRequest(BaseModel):
    comment: str | None = None


async def _resolve_reader_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _resolve_writer_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _require_mock_user(mock_user_id: str | None) -> str:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return mock_user_id.strip()


async def list_promotions_route_data(
    request: Request,
    status: str,
    page: int,
    size: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    reader = getattr(request.app.state, "promotion_list_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(status=status, page=page, size=size, user_id=user_id))
        else:
            data = await list_promotions(
                request.app.state.db_engine,
                PromotionListQuery(status=status, page=page, size=size, user_id=user_id),
            )
    except PromotionQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def list_pending_promotions_route_data(
    request: Request,
    page: int,
    size: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    reader = getattr(request.app.state, "promotion_pending_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(page=page, size=size, user_id=user_id))
        else:
            data = await list_pending_promotions(request.app.state.db_engine, page=page, size=size, user_id=user_id)
    except PromotionQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def get_promotion_detail_route_data(
    request: Request,
    promotion_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    reader = getattr(request.app.state, "promotion_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(promotion_id, user_id))
        else:
            data = await read_promotion_detail(request.app.state.db_engine, promotion_id=promotion_id, user_id=user_id)
    except PromotionQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def submit_promotion_route_data(
    request: Request,
    body: dict[str, Any] | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    if body is None:
        raise HTTPException(status_code=422, detail="body.required")
    try:
        parsed_body = PromotionRequestBody.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    promotion_input = PromotionSubmitInput(
        source_skill_id=parsed_body.sourceSkillId,
        source_version_id=parsed_body.sourceVersionId,
        target_namespace_id=parsed_body.targetNamespaceId,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "promotion_submit_writer", None)
    try:
        if writer is not None:
            data = await _resolve_writer_result(writer(promotion_input))
        else:
            data = await submit_promotion(request.app.state.db_engine, promotion_input)
    except PromotionWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


async def reject_promotion_route_data(
    request: Request,
    promotion_id: int,
    body: PromotionActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    promotion_input = PromotionRejectInput(
        promotion_id=promotion_id,
        reviewer_id=user_id,
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "promotion_reject_writer", None)
    try:
        if writer is not None:
            data = await _resolve_writer_result(writer(promotion_input))
        else:
            data = await reject_promotion(request.app.state.db_engine, promotion_input)
    except PromotionWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def approve_promotion_route_data(
    request: Request,
    promotion_id: int,
    body: PromotionActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    promotion_input = PromotionApproveInput(
        promotion_id=promotion_id,
        reviewer_id=user_id,
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "promotion_approve_writer", None)
    try:
        if writer is not None:
            data = await _resolve_writer_result(writer(promotion_input))
        else:
            data = await approve_promotion(request.app.state.db_engine, promotion_input)
    except PromotionWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/promotions")
@router.post("/api/web/promotions")
async def submit_promotion_route(
    request: Request,
    body: dict[str, Any] | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_promotion_route_data(request, body, mock_user_id)


@router.get("/api/v1/promotions")
@router.get("/api/web/promotions")
async def list_promotions_route(
    request: Request,
    status: str = "PENDING",
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_promotions_route_data(request, status, page, size, mock_user_id)


@router.get("/api/v1/promotions/pending")
@router.get("/api/web/promotions/pending")
async def list_pending_promotions_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_pending_promotions_route_data(request, page, size, mock_user_id)


@router.get("/api/v1/promotions/{promotion_id}")
@router.get("/api/web/promotions/{promotion_id}")
async def get_promotion_detail_route(
    request: Request,
    promotion_id: int,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await get_promotion_detail_route_data(request, promotion_id, mock_user_id)


@router.post("/api/v1/promotions/{promotion_id}/approve")
@router.post("/api/web/promotions/{promotion_id}/approve")
async def approve_promotion_route(
    request: Request,
    promotion_id: int,
    body: PromotionActionRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await approve_promotion_route_data(request, promotion_id, body, mock_user_id)


@router.post("/api/v1/promotions/{promotion_id}/reject")
@router.post("/api/web/promotions/{promotion_id}/reject")
async def reject_promotion_route(
    request: Request,
    promotion_id: int,
    body: PromotionActionRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await reject_promotion_route_data(request, promotion_id, body, mock_user_id)
