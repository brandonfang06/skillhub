from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.admin.review_reports import (
    AdminReviewReportError,
    approve_admin_profile_review,
    dismiss_admin_skill_report,
    list_admin_profile_reviews,
    list_admin_skill_reports,
    reject_admin_profile_review,
    require_profile_review_reader,
    require_skill_report_reader,
    resolve_admin_skill_report,
)
from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import read_current_mock_user
from app.auth.policy import platform_roles
from app.core.response import ok


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
    user = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(user)


def _roles(user: dict[str, Any]) -> list[str]:
    return platform_roles(user)


def _user_id(user: dict[str, Any]) -> str:
    value = user.get("userId") or user.get("id")
    if value is None or str(value).strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(value)


def _payload(value: dict[str, Any] | None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return request.client.host if request.client else None


def _request_meta(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.headers.get("X-Request-Id"),
        "client_ip": _client_ip(request),
        "user_agent": request.headers.get("User-Agent"),
    }


async def _require_skill_report_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    user = await _read_current_user(request, mock_user_id)
    try:
        require_skill_report_reader(_roles(user))
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return user


async def _require_profile_review_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    user = await _read_current_user(request, mock_user_id)
    try:
        require_profile_review_reader(_roles(user))
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return user


@router.get("/api/v1/admin/skill-reports")
async def list_admin_skill_reports_route(
    request: Request,
    status: str | None = None,
    page: int = Query(default=0),
    size: int = Query(default=20),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_skill_report_user(request, x_mock_user_id)
    payload = {"status": status, "page": page, "size": size}
    reader = getattr(request.app.state, "admin_skill_report_reader", None)
    try:
        data = await _resolve_result(
            reader(payload, user)
            if reader is not None
            else list_admin_skill_reports(
                request.app.state.db_engine,
                status=status,
                page=page,
                size=size,
                platform_roles=_roles(user),
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u6210\u529f", data, request)


@router.post("/api/v1/admin/skill-reports/{report_id}/resolve")
async def resolve_admin_skill_report_route(
    request: Request,
    report_id: int,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_skill_report_user(request, x_mock_user_id)
    payload = _payload(body)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "admin_skill_report_resolver", None)
    try:
        data = await _resolve_result(
            writer(report_id, payload, user, meta)
            if writer is not None
            else resolve_admin_skill_report(
                request.app.state.db_engine,
                report_id=report_id,
                actor_user_id=_user_id(user),
                platform_roles=_roles(user),
                disposition=payload.get("disposition"),
                comment=payload.get("comment"),
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/admin/skill-reports/{report_id}/dismiss")
async def dismiss_admin_skill_report_route(
    request: Request,
    report_id: int,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_skill_report_user(request, x_mock_user_id)
    payload = _payload(body)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "admin_skill_report_dismisser", None)
    try:
        data = await _resolve_result(
            writer(report_id, payload, user, meta)
            if writer is not None
            else dismiss_admin_skill_report(
                request.app.state.db_engine,
                report_id=report_id,
                actor_user_id=_user_id(user),
                platform_roles=_roles(user),
                comment=payload.get("comment"),
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.get("/api/v1/admin/profile-reviews")
async def list_admin_profile_reviews_route(
    request: Request,
    status: str | None = None,
    page: int = Query(default=0),
    size: int = Query(default=20),
    sortDirection: str = "DESC",
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_profile_review_user(request, x_mock_user_id)
    payload = {"status": status, "page": page, "size": size, "sortDirection": sortDirection}
    reader = getattr(request.app.state, "admin_profile_review_reader", None)
    try:
        data = await _resolve_result(
            reader(payload, user)
            if reader is not None
            else list_admin_profile_reviews(
                request.app.state.db_engine,
                status=status,
                page=page,
                size=size,
                sort_direction=sortDirection,
                platform_roles=_roles(user),
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u6210\u529f", data, request)


@router.post("/api/v1/admin/profile-reviews/{request_id}/approve")
async def approve_admin_profile_review_route(
    request: Request,
    request_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_profile_review_user(request, x_mock_user_id)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "admin_profile_review_approver", None)
    try:
        data = await _resolve_result(
            writer(request_id, user, meta)
            if writer is not None
            else approve_admin_profile_review(
                request.app.state.db_engine,
                request_id=request_id,
                reviewer_id=_user_id(user),
                platform_roles=_roles(user),
                http_request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.post("/api/v1/admin/profile-reviews/{request_id}/reject")
async def reject_admin_profile_review_route(
    request: Request,
    request_id: int,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    await reject_bearer_api_token_for_admin_route(request, x_mock_user_id, authorization)
    user = await _require_profile_review_user(request, x_mock_user_id)
    payload = _payload(body)
    comment = payload.get("comment")
    if not isinstance(comment, str) or comment.strip() == "":
        raise HTTPException(status_code=400, detail="error.validation")
    meta = _request_meta(request)
    writer = getattr(request.app.state, "admin_profile_review_rejecter", None)
    try:
        data = await _resolve_result(
            writer(request_id, payload, user, meta)
            if writer is not None
            else reject_admin_profile_review(
                request.app.state.db_engine,
                request_id=request_id,
                reviewer_id=_user_id(user),
                platform_roles=_roles(user),
                comment=comment,
                http_request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except AdminReviewReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)
