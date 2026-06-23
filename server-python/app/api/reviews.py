from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.auth.context import resolve_current_user_or_401
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
from app.review.query import (
    ReviewListQuery,
    ReviewQueryError,
    ReviewDownloadResult,
    list_my_review_submissions,
    list_pending_reviews,
    list_review_tasks,
    read_review_detail,
    read_review_download_package,
    read_review_file_content,
    read_review_skill_detail,
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


async def _resolve_reader_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _require_user_id(request: Request, mock_user_id: str | None) -> str:
    user = await resolve_current_user_or_401(request, mock_user_id, None)
    return str(user["userId"])


def _validate_review_file_path(path: str | None) -> str:
    if path is None or path.strip() == "" or ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400)
    return path


async def approve_review(
    request: Request,
    review_task_id: int,
    body: ReviewActionRequest | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)

    approval_input = ReviewApproveInput(
        review_task_id=review_task_id,
        reviewer_id=user_id,
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_approve_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(approval_input)
            if writer is not None
            else approve_review_task(
                request.app.state.db_engine,
                approval_input,
                notification_fanout=getattr(request.app.state, "notification_fanout", None),
            )
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
    user_id = await _require_user_id(request, mock_user_id)

    reject_input = ReviewRejectInput(
        review_task_id=review_task_id,
        reviewer_id=user_id,
        comment=body.comment if body is not None else None,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_reject_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(reject_input)
            if writer is not None
            else reject_review_task(
                request.app.state.db_engine,
                reject_input,
                notification_fanout=getattr(request.app.state, "notification_fanout", None),
            )
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def withdraw_review(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)

    withdraw_input = ReviewWithdrawInput(
        review_task_id=review_task_id,
        user_id=user_id,
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
    user_id = await _require_user_id(request, mock_user_id)

    submit_input = ReviewSubmitInput(
        skill_version_id=body.skillVersionId,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "review_submit_writer", None)
    try:
        data = await _resolve_approval_result(
            writer(submit_input)
            if writer is not None
            else submit_review_task(
                request.app.state.db_engine,
                submit_input,
                notification_fanout=getattr(request.app.state, "notification_fanout", None),
            )
        )
    except ReviewApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


async def list_reviews(
    request: Request,
    status: str,
    namespace_id: int | None,
    page: int,
    size: int,
    sort_direction: str,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_list_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    status=status,
                    namespace_id=namespace_id,
                    page=page,
                    size=size,
                    sort_direction=sort_direction,
                    user_id=user_id,
                )
            )
        else:
            data = await list_review_tasks(
                request.app.state.db_engine,
                ReviewListQuery(
                    status=status,
                    namespace_id=namespace_id,
                    page=page,
                    size=size,
                    sort_direction=sort_direction,
                    user_id=user_id,
                ),
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def list_pending_review_route_data(
    request: Request,
    namespace_id: int,
    page: int,
    size: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_pending_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace_id=namespace_id, page=page, size=size, user_id=user_id))
        else:
            data = await list_pending_reviews(
                request.app.state.db_engine,
                namespace_id=namespace_id,
                page=page,
                size=size,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def list_my_submissions_route_data(
    request: Request,
    page: int,
    size: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_my_submissions_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(page=page, size=size, user_id=user_id))
        else:
            data = await list_my_review_submissions(
                request.app.state.db_engine,
                page=page,
                size=size,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def get_review_detail(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(review_task_id, user_id))
        else:
            data = await read_review_detail(
                request.app.state.db_engine,
                review_task_id=review_task_id,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def get_review_skill_detail(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_skill_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    getattr(request.app.state, "db_engine", None),
                    request.app.state.settings.storage_base_path,
                    review_task_id=review_task_id,
                    user_id=user_id,
                )
            )
        else:
            data = await read_review_skill_detail(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                review_task_id=review_task_id,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


async def get_review_file_content(
    request: Request,
    review_task_id: int,
    file_path: str | None,
    mock_user_id: str | None,
) -> Response:
    user_id = await _require_user_id(request, mock_user_id)
    normalized_path = _validate_review_file_path(file_path)
    reader = getattr(request.app.state, "review_file_reader", None)
    try:
        if reader is not None:
            content = await _resolve_reader_result(
                reader(
                    getattr(request.app.state, "db_engine", None),
                    request.app.state.settings.storage_base_path,
                    review_task_id=review_task_id,
                    file_path=normalized_path,
                    user_id=user_id,
                )
            )
        else:
            content = await read_review_file_content(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                review_task_id=review_task_id,
                file_path=normalized_path,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


def _build_review_download_response(result: ReviewDownloadResult) -> Response:
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Content-Length": str(result.content_length),
        },
    )


async def get_review_download(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None,
) -> Response:
    user_id = await _require_user_id(request, mock_user_id)
    reader = getattr(request.app.state, "review_download_reader", None)
    try:
        if reader is not None:
            result = await _resolve_reader_result(
                reader(
                    getattr(request.app.state, "db_engine", None),
                    request.app.state.settings.storage_base_path,
                    review_task_id=review_task_id,
                    user_id=user_id,
                )
            )
        else:
            result = await read_review_download_package(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                review_task_id=review_task_id,
                user_id=user_id,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _build_review_download_response(result)


@router.get("/api/v1/reviews")
@router.get("/api/web/reviews")
async def list_reviews_route(
    request: Request,
    status: str,
    namespace_id: int | None = Query(default=None, alias="namespaceId"),
    page: int = 0,
    size: int = 20,
    sort_direction: str = Query(default="DESC", alias="sortDirection"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_reviews(request, status, namespace_id, page, size, sort_direction, mock_user_id)


@router.get("/api/v1/reviews/pending")
@router.get("/api/web/reviews/pending")
async def list_pending_reviews_route(
    request: Request,
    namespace_id: int = Query(alias="namespaceId"),
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_pending_review_route_data(request, namespace_id, page, size, mock_user_id)


@router.get("/api/v1/reviews/my-submissions")
@router.get("/api/web/reviews/my-submissions")
async def list_my_submissions_route(
    request: Request,
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await list_my_submissions_route_data(request, page, size, mock_user_id)


@router.get("/api/v1/reviews/{review_task_id}/skill-detail")
@router.get("/api/web/reviews/{review_task_id}/skill-detail")
async def get_review_skill_detail_route(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await get_review_skill_detail(request, review_task_id, mock_user_id)


@router.get("/api/v1/reviews/{review_task_id}/file")
@router.get("/api/web/reviews/{review_task_id}/file")
async def get_review_file_route(
    request: Request,
    review_task_id: int,
    path: str | None = Query(default=None),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await get_review_file_content(request, review_task_id, path, mock_user_id)


@router.get("/api/v1/reviews/{review_task_id}/download")
@router.get("/api/web/reviews/{review_task_id}/download")
async def get_review_download_route(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await get_review_download(request, review_task_id, mock_user_id)


@router.get("/api/v1/reviews/{review_task_id}")
@router.get("/api/web/reviews/{review_task_id}")
async def get_review_detail_route(
    request: Request,
    review_task_id: int,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await get_review_detail(request, review_task_id, mock_user_id)


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
