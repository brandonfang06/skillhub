from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.response import ok
from app.review.approval import (
    ReviewApprovalError,
    ReviewApproveInput,
    ReviewRejectInput,
    ReviewSubmitInput,
    ReviewWithdrawInput,
    approve_review_task,
    reject_review_task,
    submit_review_task,
    withdraw_review_task,
)


router = APIRouter()


class ReviewActionRequest(BaseModel):
    comment: str | None = None


class ReviewSubmitRequest(BaseModel):
    skillVersionId: int


async def _resolve_approval_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def approve_review(
    request: Request,
    review_task_id: int,
    body: ReviewActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    approval_input = ReviewApproveInput(
        review_task_id=review_task_id,
        reviewer_id=mock_user_id.strip(),
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_approve_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(approval_input) if writer is not None else approve_review_task(request.app.state.db_engine, approval_input)
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def reject_review(
    request: Request,
    review_task_id: int,
    body: ReviewActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    reject_input = ReviewRejectInput(
        review_task_id=review_task_id,
        reviewer_id=mock_user_id.strip(),
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_reject_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(reject_input) if writer is not None else reject_review_task(request.app.state.db_engine, reject_input)
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def withdraw_review(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    withdraw_input = ReviewWithdrawInput(
        review_task_id=review_task_id,
        user_id=mock_user_id.strip(),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_withdraw_writer", None)
    try:
        await _resolve_approval_result(
            writer(withdraw_input) if writer is not None else withdraw_review_task(request.app.state.db_engine, withdraw_input)
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", None, request)


async def submit_review(
    request: Request,
    body: ReviewSubmitRequest,
    mock_user_id: str | None,
) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    submit_input = ReviewSubmitInput(
        skill_version_id=body.skillVersionId,
        user_id=mock_user_id.strip(),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_submit_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(submit_input) if writer is not None else submit_review_task(request.app.state.db_engine, submit_input)
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.post("/api/v1/reviews")
@router.post("/api/web/reviews")
async def submit_review_route(
    request: Request,
    body: ReviewSubmitRequest,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_review(request, body, mock_user_id)


@router.post("/api/v1/reviews/{review_task_id}/approve")
@router.post("/api/web/reviews/{review_task_id}/approve")
async def approve_review_route(
    request: Request,
    review_task_id: int,
    body: ReviewActionRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await approve_review(request, review_task_id, body, mock_user_id)


@router.post("/api/v1/reviews/{review_task_id}/reject")
@router.post("/api/web/reviews/{review_task_id}/reject")
async def reject_review_route(
    request: Request,
    review_task_id: int,
    body: ReviewActionRequest | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await reject_review(request, review_task_id, body, mock_user_id)


@router.post("/api/v1/reviews/{review_task_id}/withdraw")
@router.post("/api/web/reviews/{review_task_id}/withdraw")
async def withdraw_review_route(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await withdraw_review(request, review_task_id, mock_user_id)
