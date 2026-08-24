from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from inspect import isawaitable
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, Response

from app.api.admin_policy import reject_bearer_api_token_for_admin_route
from app.auth.context import resolve_current_user_or_401
from app.auth.policy import require_platform_role
from app.core.response import ok
from app.namespace_analytics.contracts import NamespaceAnalyticsEnvelope
from app.namespace_analytics.repository import (
    NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT,
    NamespaceAnalyticsError,
    export_namespace_analytics_csv,
    list_namespace_analytics,
)
from app.namespace_analytics.security_contracts import (
    NamespaceSecurityAnalyticsEnvelope,
    NamespaceSecuritySkillsEnvelope,
)

router = APIRouter(tags=["Namespace Analytics"])


async def _resolve_result(result: object | Awaitable[object]) -> object:
    if isawaitable(result):
        return await result
    return result


@router.get(
    "/api/v1/admin/namespace-analytics",
    response_model=NamespaceAnalyticsEnvelope,
)
async def list_namespace_analytics_route(
    request: Request,
    query: str | None = None,
    namespaceType: Literal["ALL", "TEAM", "GLOBAL"] = "ALL",
    namespaceStatus: Literal["ALL", "ACTIVE", "FROZEN", "ARCHIVED"] = "ACTIVE",
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    source: Literal["web", "cli", "api"] | None = None,
    sort: Literal["namespace", "maintainers", "skills", "lifetimeDownloads", "periodDownloads"] = "periodDownloads",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
    settings = getattr(request.app.state, "settings", None)
    retention_months = int(getattr(settings, "download_analytics_retention_months", 12))
    try:
        data = await list_namespace_analytics(
            request.app.state.db_engine,
            query=query,
            namespace_type=namespaceType,
            namespace_status=namespaceStatus,
            start_time=startTime,
            end_time=endTime,
            source=source,
            sort=sort,
            direction=direction,
            page=page,
            size=size,
            retention_months=retention_months,
        )
    except NamespaceAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.read", data, request)


@router.get("/api/v1/admin/namespace-analytics.csv")
async def export_namespace_analytics_csv_route(
    request: Request,
    query: str | None = None,
    namespaceType: Literal["ALL", "TEAM", "GLOBAL"] = "ALL",
    namespaceStatus: Literal["ALL", "ACTIVE", "FROZEN", "ARCHIVED"] = "ACTIVE",
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    source: Literal["web", "cli", "api"] | None = None,
    sort: Literal["namespace", "maintainers", "skills", "lifetimeDownloads", "periodDownloads"] = "periodDownloads",
    direction: Literal["asc", "desc"] = "desc",
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
    try:
        csv_body, truncated = await export_namespace_analytics_csv(
            request.app.state.db_engine,
            query=query,
            namespace_type=namespaceType,
            namespace_status=namespaceStatus,
            start_time=startTime,
            end_time=endTime,
            source=source,
            sort=sort,
            direction=direction,
        )
    except NamespaceAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="skillhub-namespace-analytics.csv"',
            "X-SkillHub-Export-Truncated": str(truncated).lower(),
            "X-SkillHub-Export-Row-Limit": str(NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT),
        },
    )


@router.get(
    "/api/v1/admin/namespace-analytics/security",
    response_model=NamespaceSecurityAnalyticsEnvelope,
)
async def list_namespace_security_analytics_route(
    request: Request,
    query: str | None = None,
    severity: Literal["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNCLASSIFIED"] = "ALL",
    namespaceType: Literal["ALL", "TEAM", "GLOBAL"] = "ALL",
    namespaceStatus: Literal["ALL", "ACTIVE", "FROZEN", "ARCHIVED"] = "ALL",
    skillStatus: Literal["ALL", "ACTIVE", "ARCHIVED"] = "ALL",
    visibility: Literal["ALL", "PUBLIC", "NAMESPACE_ONLY", "PRIVATE"] = "ALL",
    hidden: Literal["ALL", "VISIBLE", "HIDDEN"] = "ALL",
    versionStatus: Literal[
        "ALL",
        "DRAFT",
        "SCANNING",
        "SCAN_FAILED",
        "UPLOADED",
        "PENDING_REVIEW",
        "PUBLISHED",
        "REJECTED",
        "YANKED",
    ] = "ALL",
    scannerType: Literal["skill-scanner", "custom"] | None = None,
    sort: Literal[
        "risk",
        "namespace",
        "affectedSkills",
        "affectedVersions",
        "findings",
        "latestScan",
    ] = "risk",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
    params = {
        "query": query,
        "severity": severity,
        "namespace_type": namespaceType,
        "namespace_status": namespaceStatus,
        "skill_status": skillStatus,
        "visibility": visibility,
        "hidden": hidden,
        "version_status": versionStatus,
        "scanner_type": scannerType,
        "sort": sort,
        "direction": direction,
        "page": page,
        "size": size,
    }
    reader = getattr(request.app.state, "namespace_security_analytics_reader", None)
    if reader is not None:
        data = await _resolve_result(reader(**params))
    else:
        from app.namespace_analytics.security_repository import (
            list_namespace_security_analytics,
        )

        data = await list_namespace_security_analytics(request.app.state.db_engine, **params)
    return ok("response.success.read", data, request)


@router.get(
    "/api/v1/admin/namespace-analytics/security/namespaces/{namespace_id}/skills",
    response_model=NamespaceSecuritySkillsEnvelope,
)
async def list_namespace_security_skills_route(
    request: Request,
    namespace_id: int = Path(ge=1),
    query: str | None = None,
    severity: Literal["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNCLASSIFIED"] = "ALL",
    skillStatus: Literal["ALL", "ACTIVE", "ARCHIVED"] = "ALL",
    visibility: Literal["ALL", "PUBLIC", "NAMESPACE_ONLY", "PRIVATE"] = "ALL",
    hidden: Literal["ALL", "VISIBLE", "HIDDEN"] = "ALL",
    versionStatus: Literal[
        "ALL",
        "DRAFT",
        "SCANNING",
        "SCAN_FAILED",
        "UPLOADED",
        "PENDING_REVIEW",
        "PUBLISHED",
        "REJECTED",
        "YANKED",
    ] = "ALL",
    scannerType: Literal["skill-scanner", "custom"] | None = None,
    sort: Literal["risk", "skill", "affectedVersions", "findings", "latestScan"] = "risk",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    await reject_bearer_api_token_for_admin_route(request, mock_user_id, authorization)
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
    params = {
        "namespace_id": namespace_id,
        "query": query,
        "severity": severity,
        "skill_status": skillStatus,
        "visibility": visibility,
        "hidden": hidden,
        "version_status": versionStatus,
        "scanner_type": scannerType,
        "sort": sort,
        "direction": direction,
        "page": page,
        "size": size,
    }
    reader = getattr(request.app.state, "namespace_security_skills_reader", None)
    if reader is not None:
        data = await _resolve_result(reader(**params))
    else:
        from app.namespace_analytics.security_repository import (
            list_namespace_security_skills,
        )

        data = await list_namespace_security_skills(request.app.state.db_engine, **params)
    return ok("response.success.read", data, request)
