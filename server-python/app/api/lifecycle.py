from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.auth.context import read_current_mock_user, resolve_current_user_or_401
from app.auth.policy import is_api_token_principal, reject_api_token_principal_for_route, require_api_token_scope
from app.core.response import ok
from app.lifecycle.hard_delete import SkillHardDeleteError, SkillHardDeleteInput, hard_delete_skill
from app.lifecycle.skill import (
    SkillArchiveInput,
    SkillConfirmPublishInput,
    SkillLifecycleError,
    SkillRereleaseInput,
    SkillSubmitReviewInput,
    SkillVersionDeleteInput,
    SkillVersionWithdrawReviewInput,
    archive_skill as archive_skill_workflow,
    cleanup_deleted_version_storage,
    confirm_publish_skill_version,
    delete_skill_version,
    rerelease_skill_version,
    submit_skill_version_for_review,
    unarchive_skill as unarchive_skill_workflow,
    withdraw_skill_version_review,
)


router = APIRouter()


class SkillArchiveRequest(BaseModel):
    reason: str | None = None


class SkillConfirmPublishRequest(BaseModel):
    version: str


class SkillSubmitReviewRequest(BaseModel):
    version: str
    targetVisibility: str


class SkillRereleaseRequest(BaseModel):
    targetVersion: str
    confirmWarnings: bool = False


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _require_mock_user(mock_user_id: str | None) -> str:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return mock_user_id.strip()


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, object]:
    user_id = _require_mock_user(mock_user_id)
    reader = getattr(request.app.state, "auth_me_reader", None)
    data = await _resolve_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


async def _read_hard_delete_user(
    request: Request,
    route_scope: str,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, object]:
    user = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    if is_api_token_principal(user):
        if route_scope not in {"v1", "cli"}:
            reject_api_token_principal_for_route(user, request.url.path)
        require_api_token_scope(user, "skill:delete")
    return user


def _settings_storage_base_path(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        return str(settings.storage_base_path)
    return str(getattr(request.app.state, "storage_base_path", ""))


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


async def delete_skill_version_route_data(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    delete_input = SkillVersionDeleteInput(
        namespace=namespace,
        slug=slug,
        version=version,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_delete_version_writer", None)
    try:
        result = await _resolve_result(
            writer(delete_input) if writer is not None else delete_skill_version(request.app.state.db_engine, delete_input)
        )
        storage_cleanup = getattr(request.app.state, "skill_delete_storage_cleanup", None)
        if storage_cleanup is not None:
            await _resolve_result(storage_cleanup(request.app.state.db_engine, request.app.state.settings.storage_base_path, result))
        else:
            await cleanup_deleted_version_storage(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                result,
            )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", result.response, request)


async def hard_delete_skill_route_data(
    request: Request,
    route_scope: str,
    *,
    skill_id: int | None,
    namespace: str | None,
    slug: str | None,
    owner_id: str | None,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = await _read_hard_delete_user(request, route_scope, mock_user_id, authorization)
    if route_scope == "v1" and "SUPER_ADMIN" not in {str(role) for role in user.get("platformRoles", [])}:
        raise HTTPException(status_code=403, detail="error.admin.superAdminRequired")
    delete_input = SkillHardDeleteInput(
        route_scope=route_scope,
        skill_id=skill_id,
        namespace=namespace,
        slug=slug,
        owner_id=owner_id,
        actor_user_id=str(user["userId"]),
        actor_platform_roles=[str(role) for role in user.get("platformRoles", [])],
        storage_base_path=_settings_storage_base_path(request),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_hard_delete_writer", None)
    try:
        data = await _resolve_result(
            writer(delete_input)
            if writer is not None
            else hard_delete_skill(request.app.state.db_engine, delete_input)
        )
    except SkillHardDeleteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)


def _cli_delete_response(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(data.get("deleted")),
        "scope": "remote",
        "action": "delete",
        "namespace": data.get("namespace"),
        "slug": data.get("slug"),
    }


async def cli_delete_skill_route_data(
    request: Request,
    namespace: str,
    slug: str,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    response = await hard_delete_skill_route_data(
        request,
        "cli",
        skill_id=None,
        namespace=namespace,
        slug=slug,
        owner_id=None,
        mock_user_id=mock_user_id,
        authorization=authorization,
    )
    response["data"] = _cli_delete_response(dict(response["data"]))
    return response


async def withdraw_skill_version_review_route_data(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    withdraw_input = SkillVersionWithdrawReviewInput(
        namespace=namespace,
        slug=slug,
        version=version,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_withdraw_review_writer", None)
    try:
        data = await _resolve_result(
            writer(withdraw_input)
            if writer is not None
            else withdraw_skill_version_review(request.app.state.db_engine, withdraw_input)
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def confirm_publish_route_data(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillConfirmPublishRequest,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    confirm_input = SkillConfirmPublishInput(
        namespace=namespace,
        slug=slug,
        version=body.version,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_confirm_publish_writer", None)
    try:
        data = await _resolve_result(
            writer(confirm_input)
            if writer is not None
            else confirm_publish_skill_version(request.app.state.db_engine, confirm_input)
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def submit_review_route_data(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillSubmitReviewRequest,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    submit_input = SkillSubmitReviewInput(
        namespace=namespace,
        slug=slug,
        version=body.version,
        target_visibility=body.targetVisibility,
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_submit_review_writer", None)
    try:
        data = await _resolve_result(
            writer(submit_input)
            if writer is not None
            else submit_skill_version_for_review(request.app.state.db_engine, submit_input)
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


async def rerelease_route_data(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    body: SkillRereleaseRequest,
    mock_user_id: str | None,
) -> dict[str, Any]:
    user_id = _require_mock_user(mock_user_id)
    settings = getattr(request.app.state, "settings", None)
    rerelease_input = SkillRereleaseInput(
        namespace=namespace,
        slug=slug,
        version=version,
        target_version=body.targetVersion,
        confirm_warnings=body.confirmWarnings,
        user_id=user_id,
        storage_base_path=settings.storage_base_path if settings is not None else "",
        scanner_enabled=bool(getattr(settings, "security_scanner_enabled", False)) if settings is not None else False,
        scan_mode=str(getattr(settings, "security_scanner_mode", "local")) if settings is not None else "local",
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    writer = getattr(request.app.state, "skill_rerelease_writer", None)
    try:
        data = await _resolve_result(
            writer(rerelease_input)
            if writer is not None
            else rerelease_skill_version(request.app.state.db_engine, rerelease_input)
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


@router.delete("/api/v1/skills/id/{skill_id}")
async def hard_delete_skill_by_id_v1(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await hard_delete_skill_route_data(
        request,
        "v1",
        skill_id=skill_id,
        namespace=None,
        slug=None,
        owner_id=None,
        mock_user_id=x_mock_user_id,
        authorization=authorization,
    )


@router.delete("/api/web/skills/id/{skill_id}")
async def hard_delete_skill_by_id_web(
    request: Request,
    skill_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await hard_delete_skill_route_data(
        request,
        "web",
        skill_id=skill_id,
        namespace=None,
        slug=None,
        owner_id=None,
        mock_user_id=x_mock_user_id,
        authorization=authorization,
    )


@router.delete("/api/v1/skills/{namespace}/{slug}")
async def hard_delete_skill_v1(
    request: Request,
    namespace: str,
    slug: str,
    ownerId: str | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await hard_delete_skill_route_data(
        request,
        "v1",
        skill_id=None,
        namespace=namespace,
        slug=slug,
        owner_id=ownerId,
        mock_user_id=x_mock_user_id,
        authorization=authorization,
    )


@router.delete("/api/web/skills/{namespace}/{slug}")
async def hard_delete_skill_web(
    request: Request,
    namespace: str,
    slug: str,
    ownerId: str | None = None,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await hard_delete_skill_route_data(
        request,
        "web",
        skill_id=None,
        namespace=namespace,
        slug=slug,
        owner_id=ownerId,
        mock_user_id=x_mock_user_id,
        authorization=authorization,
    )


@router.delete("/api/cli/v1/skills/{namespace}/{slug}")
async def cli_delete_skill(
    request: Request,
    namespace: str,
    slug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await cli_delete_skill_route_data(request, namespace, slug, x_mock_user_id, authorization)


@router.delete("/api/v1/skills/{namespace}/{slug}/versions/{version}")
async def delete_skill_version_v1(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await delete_skill_version_route_data(request, namespace, slug, version, x_mock_user_id)


@router.delete("/api/web/skills/{namespace}/{slug}/versions/{version}")
async def delete_skill_version_web(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await delete_skill_version_route_data(request, namespace, slug, version, x_mock_user_id)


@router.post("/api/v1/skills/{namespace}/{slug}/versions/{version}/withdraw-review")
async def withdraw_skill_version_review_v1(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await withdraw_skill_version_review_route_data(request, namespace, slug, version, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/versions/{version}/withdraw-review")
async def withdraw_skill_version_review_web(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await withdraw_skill_version_review_route_data(request, namespace, slug, version, x_mock_user_id)


@router.post("/api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease")
async def rerelease_v1(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    body: SkillRereleaseRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await rerelease_route_data(request, namespace, slug, version, body, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/versions/{version}/rerelease")
async def rerelease_web(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    body: SkillRereleaseRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await rerelease_route_data(request, namespace, slug, version, body, x_mock_user_id)


@router.post("/api/v1/skills/{namespace}/{slug}/confirm-publish")
async def confirm_publish_v1(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillConfirmPublishRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await confirm_publish_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/confirm-publish")
async def confirm_publish_web(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillConfirmPublishRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await confirm_publish_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/v1/skills/{namespace}/{slug}/submit-review")
async def submit_review_v1(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillSubmitReviewRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_review_route_data(request, namespace, slug, body, x_mock_user_id)


@router.post("/api/web/skills/{namespace}/{slug}/submit-review")
async def submit_review_web(
    request: Request,
    namespace: str,
    slug: str,
    body: SkillSubmitReviewRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    return await submit_review_route_data(request, namespace, slug, body, x_mock_user_id)
