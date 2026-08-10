from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import platform_roles
from app.core.response import ok
from app.download_analytics.repository import (
    DOWNLOAD_EVENT_CSV_EXPORT_LIMIT,
    DownloadAnalyticsError,
    export_admin_download_events_csv,
    list_admin_download_events,
    list_skill_download_events,
)

router = APIRouter(tags=["Download Analytics"])


@router.get("/api/v1/admin/download-events")
async def list_admin_download_events_route(
    request: Request,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    namespace: str | None = None,
    slug: str | None = None,
    version: str | None = None,
    userId: str | None = None,
    userQuery: str | None = None,
    source: str | None = None,
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    try:
        data = await list_admin_download_events(
            request.app.state.db_engine,
            page=page,
            size=size,
            namespace=namespace,
            slug=slug,
            version=version,
            user_id=userId,
            user_query=userQuery,
            source=source,
            start_time=startTime,
            end_time=endTime,
            platform_roles=platform_roles(user),
        )
    except DownloadAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.get("/api/v1/admin/download-events.csv")
async def export_admin_download_events_csv_route(
    request: Request,
    namespace: str | None = None,
    slug: str | None = None,
    version: str | None = None,
    userId: str | None = None,
    userQuery: str | None = None,
    source: str | None = None,
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    try:
        csv_body, truncated = await export_admin_download_events_csv(
            request.app.state.db_engine,
            namespace=namespace,
            slug=slug,
            version=version,
            user_id=userId,
            user_query=userQuery,
            source=source,
            start_time=startTime,
            end_time=endTime,
            platform_roles=platform_roles(user),
        )
    except DownloadAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="skillhub-download-events.csv"',
            "X-SkillHub-Export-Truncated": str(truncated).lower(),
            "X-SkillHub-Export-Row-Limit": str(DOWNLOAD_EVENT_CSV_EXPORT_LIMIT),
        },
    )


@router.get("/api/web/skills/{namespace}/{slug}/download-events")
async def list_skill_download_events_route(
    namespace: str,
    slug: str,
    request: Request,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    version: str | None = None,
    userId: str | None = None,
    source: str | None = None,
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    try:
        data = await list_skill_download_events(
            request.app.state.db_engine,
            namespace=namespace,
            slug=slug,
            page=page,
            size=size,
            version=version,
            user_id=userId,
            source=source,
            start_time=startTime,
            end_time=endTime,
            actor_user_id=str(user["userId"]),
            platform_roles=platform_roles(user),
        )
    except DownloadAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)
