from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import read_current_mock_user
from app.core.response import ok
from app.reports.skill_reports import SkillReportSubmitError, submit_skill_report


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


async def submit_skill_report_route_data(
    request: Request,
    namespace: str,
    slug: str,
    body: dict[str, Any] | None,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user = await _read_current_user(request, mock_user_id)
    payload = _payload(body)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "skill_report_submitter", None)
    try:
        data = await _resolve_result(
            writer(namespace, slug, payload, user, meta)
            if writer is not None
            else submit_skill_report(
                request.app.state.db_engine,
                namespace_slug=namespace,
                skill_slug=slug,
                reporter_id=_user_id(user),
                reason=payload.get("reason"),
                details=payload.get("details"),
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
                notification_fanout=getattr(request.app.state, "notification_fanout", None),
            )
        )
    except SkillReportSubmitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u521b\u5efa\u6210\u529f", data, request)


@router.post("/api/v1/skills/{namespace}/{slug}/reports")
async def submit_skill_report_v1_route(
    request: Request,
    namespace: str,
    slug: str,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_skill_report_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/reports")
async def submit_skill_report_web_route(
    request: Request,
    namespace: str,
    slug: str,
    body: dict[str, Any] | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_skill_report_route_data(request, namespace, slug, body, x_mock_user_id)
