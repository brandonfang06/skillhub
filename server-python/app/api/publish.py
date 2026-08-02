from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile

from app.auth.context import resolve_current_user_or_401
from app.auth.policy import platform_roles, require_api_token_scope
from app.core.config import get_settings
from app.core.response import ok
from app.core.redis import create_redis_client
from app.object_storage import object_storage_for_settings
from app.publish.dry_run import (
    PublishDryRunInput,
    PublishDryRunRepository,
    PublishDryRunResult,
    validate_publish_dry_run,
)
from app.publish.orchestration import PublishWriteInput, PublishWriteResult, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata, determine_content_type, extract_package, normalize_entry_path, validate_package
from app.publish.replacement import ReplaceableVersion, VersionReplacementConflict, find_replaceable_version
from app.publish.scanner_handoff import RedisScanTaskPublisher

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

VALID_VISIBILITIES = {"PUBLIC", "PRIVATE", "NAMESPACE_ONLY"}
GLOBAL_NAMESPACE = "global"


def normalize_visibility(raw: str | None) -> str:
    visibility = (raw or "PUBLIC").upper()
    if visibility not in VALID_VISIBILITIES:
        raise HTTPException(status_code=400, detail="error.skill.publish.visibility.invalid")
    return visibility


def dry_run_response(result: PublishDryRunResult) -> dict[str, object]:
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "resolvedSlug": result.resolved_slug,
        "resolvedVersion": result.resolved_version,
    }


def publish_response(namespace: str, slug: str, version: str, visibility: str) -> dict[str, object]:
    return {
        "namespace": namespace,
        "slug": slug,
        "version": version,
        "visibility": visibility,
    }


def compat_publish_response(result: PublishWriteResult) -> dict[str, object]:
    return {"ok": True, "skillId": str(result.skill_id), "versionId": str(result.version_id)}


def normalize_namespace(namespace: str | None) -> str:
    normalized = (namespace or "").strip()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    return normalized or GLOBAL_NAMESPACE


def log_publish_validation_rejection(
    request: Request,
    *,
    namespace: str,
    publisher_id: str,
    visibility: str,
    result: PublishDryRunResult,
) -> None:
    logger.warning(
        "Skill publish validation rejected request_id=%s publisher_id=%s namespace=%s visibility=%s errors=%s warnings=%s",
        getattr(request.state, "request_id", None),
        publisher_id,
        namespace,
        visibility,
        result.errors,
        result.warnings,
    )


def namespace_from_payload(payload: dict[str, object] | None) -> str:
    if not payload:
        return GLOBAL_NAMESPACE

    raw_namespace = payload.get("namespace")
    if isinstance(raw_namespace, str) and raw_namespace.strip():
        return normalize_namespace(raw_namespace)

    raw_slug = payload.get("slug")
    if isinstance(raw_slug, str) and "--" in raw_slug:
        return normalize_namespace(raw_slug.split("--", 1)[0])

    return GLOBAL_NAMESPACE


async def extract_multipart_files(files: list[UploadFile]) -> list[PackageEntry]:
    entries: list[PackageEntry] = []
    seen_paths: set[str] = set()
    for file in files:
        if file.filename is None or file.filename.strip() == "":
            continue
        try:
            path = normalize_entry_path(file.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc
        if path in seen_paths:
            raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid")
        seen_paths.add(path)
        content = await file.read()
        entries.append(PackageEntry(path=path, content=content, content_type=determine_content_type(path)))
    return entries


async def resolve_current_user(request: Request, mock_user_id: str | None, authorization: str | None) -> dict[str, object]:
    data = dict(await resolve_current_user_or_401(request, mock_user_id, authorization))
    require_api_token_scope(data, "skill:publish")
    return data


async def resolve_publish_validate_result(result: PublishDryRunResult | Awaitable[PublishDryRunResult]) -> PublishDryRunResult:
    if isawaitable(result):
        return await result
    return result


async def run_publish_validate(
    request: Request,
    namespace: str,
    entries: list[PackageEntry],
    publisher_id: str,
    visibility: str,
    platform_roles: set[str],
) -> PublishDryRunResult:
    reader = getattr(request.app.state, "publish_validate_reader", None)
    if reader is not None:
        return await resolve_publish_validate_result(reader(namespace, entries, publisher_id, visibility, platform_roles))

    repository = PublishDryRunRepository(request.app.state.db_engine)
    settings = getattr(request.app.state, "settings", get_settings())
    allowed_extensions = getattr(settings, "publish_allowed_file_extensions", None)
    return await validate_publish_dry_run(
        PublishDryRunInput(
            namespace_slug=namespace,
            entries=entries,
            publisher_id=publisher_id,
            visibility=visibility,
            platform_roles=platform_roles,
            allowed_extensions=allowed_extensions,
        ),
        repository,
    )


async def resolve_namespace_id_for_write(
    request: Request,
    namespace: str,
    publisher_id: str,
    platform_roles: set[str],
) -> int:
    namespace_reader = getattr(request.app.state, "publish_namespace_context_reader", None)
    if namespace_reader is not None:
        context = namespace_reader(namespace, publisher_id, platform_roles)
        if isawaitable(context):
            context = await context
        return int(context.namespace_id)

    if getattr(request.app.state, "publish_write_reader", None) is not None:
        return int(getattr(request.app.state, "publish_write_namespace_id", 0))

    repository = PublishDryRunRepository(request.app.state.db_engine)
    context = await repository.read_namespace_context(namespace, publisher_id, platform_roles)
    if context is None:
        raise HTTPException(status_code=400, detail=f"Namespace not found: {namespace}")
    return context.namespace_id


async def resolve_publish_write_result(result: PublishWriteResult | Awaitable[PublishWriteResult]) -> PublishWriteResult:
    if isawaitable(result):
        return await result
    return result


async def resolve_replaceable_version(
    result: ReplaceableVersion | None | Awaitable[ReplaceableVersion | None],
) -> ReplaceableVersion | None:
    if isawaitable(result):
        return await result
    return result


async def find_publish_replacement(
    request: Request,
    namespace_id: int,
    namespace: str,
    slug: str,
    version: str,
    publisher_id: str,
) -> ReplaceableVersion | None:
    reader = getattr(request.app.state, "publish_replacement_reader", None)
    if reader is not None:
        return await resolve_replaceable_version(reader(namespace_id, namespace, slug, version, publisher_id))

    if getattr(request.app.state, "publish_write_reader", None) is not None:
        return None

    async with request.app.state.db_engine.connect() as connection:
        return await find_replaceable_version(
            connection,
            namespace_id=namespace_id,
            namespace=namespace,
            slug=slug,
            version=version,
            publisher_id=publisher_id,
        )


async def run_publish_write(request: Request, write_input: PublishWriteInput) -> PublishWriteResult:
    writer = getattr(request.app.state, "publish_write_reader", None)
    if writer is not None:
        return await resolve_publish_write_result(writer(write_input))
    scan_task_publisher = getattr(request.app.state, "publish_scan_task_publisher", None)
    if write_input.scanner_enabled and scan_task_publisher is None:
        settings = getattr(request.app.state, "settings", get_settings())
        redis_client = getattr(request.app.state, "redis_client", None)
        if redis_client is None:
            redis_client = create_redis_client(settings)
            request.app.state.redis_client = redis_client
        scan_task_publisher = RedisScanTaskPublisher(redis_client, settings.scan_stream_key)
    return await execute_publish_write(
        request.app.state.db_engine,
        write_input,
        scan_task_publisher=scan_task_publisher,
        notification_fanout=getattr(request.app.state, "notification_fanout", None),
    )


async def publish_entries(
    request: Request,
    namespace: str,
    entries: list[PackageEntry],
    mock_user_id: str | None,
    authorization: str | None,
    visibility: str | None,
    *,
    compat_namespace: str | None = None,
    compat_slug: str | None = None,
) -> tuple[PublishDryRunResult, PublishWriteResult, str]:
    user = await resolve_current_user(request, mock_user_id, authorization)
    resolved_visibility = normalize_visibility(visibility)
    platform_role_set = set(platform_roles(user))
    publisher_id = str(user["userId"])

    dry_run = await run_publish_validate(request, namespace, entries, publisher_id, resolved_visibility, platform_role_set)
    if not dry_run.valid:
        log_publish_validation_rejection(
            request,
            namespace=namespace,
            publisher_id=publisher_id,
            visibility=resolved_visibility,
            result=dry_run,
        )
        messages = dry_run.errors or dry_run.warnings
        raise HTTPException(status_code=400, detail=", ".join(messages))
    if dry_run.resolved_slug is None or dry_run.resolved_version is None:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid")

    settings = getattr(request.app.state, "settings", get_settings())
    allowed_extensions = getattr(settings, "publish_allowed_file_extensions", None)
    package_validation = validate_package(entries, allowed_extensions=allowed_extensions)
    metadata = package_validation.metadata
    if metadata is None:
        raise HTTPException(status_code=400, detail="error.skill.publish.skillMd.notFound")

    namespace_id = await resolve_namespace_id_for_write(request, namespace, publisher_id, platform_role_set)
    replacement = await find_publish_replacement(
        request,
        namespace_id,
        namespace,
        dry_run.resolved_slug,
        dry_run.resolved_version,
        publisher_id,
    )
    write_input = PublishWriteInput(
        namespace_id=namespace_id,
        namespace_slug=namespace,
        slug=dry_run.resolved_slug,
        display_name=metadata.name,
        summary=metadata.description,
        publisher_id=publisher_id,
        visibility=resolved_visibility,
        version=dry_run.resolved_version,
        auto_publish=(
            "SUPER_ADMIN" in platform_role_set
            and (replacement is None or replacement.status != "REJECTED")
        ),
        metadata=metadata_with_resolved_version(metadata, dry_run.resolved_version),
        entries=entries,
        storage_base_path=settings.storage_base_path,
        storage=object_storage_for_settings(settings),
        scanner_enabled=settings.security_scanner_enabled,
        scan_mode=settings.security_scanner_mode,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        compat_namespace=compat_namespace,
        compat_slug=compat_slug,
        replacement=replacement,
    )
    try:
        result = await run_publish_write(request, write_input)
    except VersionReplacementConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return dry_run, result, resolved_visibility


def metadata_with_resolved_version(metadata: SkillMetadata, resolved_version: str) -> SkillMetadata:
    if metadata.version == resolved_version:
        return metadata
    frontmatter = dict(metadata.frontmatter)
    frontmatter["version"] = resolved_version
    return SkillMetadata(
        name=metadata.name,
        description=metadata.description,
        version=resolved_version,
        frontmatter=frontmatter,
    )


@router.post("/api/cli/v1/skills/{namespace}/publish/validate")
async def validate_cli_publish(
    request: Request,
    namespace: str,
    file: UploadFile = File(...),
    visibility: str | None = Form(default=None),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await resolve_current_user(request, mock_user_id, authorization)
    resolved_visibility = normalize_visibility(visibility)

    try:
        entries = extract_package(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc

    result = await run_publish_validate(
        request,
        namespace,
        entries,
        str(user["userId"]),
        resolved_visibility,
        set(platform_roles(user)),
    )
    if not result.valid:
        log_publish_validation_rejection(
            request,
            namespace=namespace,
            publisher_id=str(user["userId"]),
            visibility=resolved_visibility,
            result=result,
        )
    return ok("response.success.read", dry_run_response(result), request)


@router.post("/api/cli/v1/skills/{namespace}/publish")
@router.post("/api/v1/skills/{namespace}/publish")
@router.post("/api/web/skills/{namespace}/publish")
async def publish_cli_skill(
    request: Request,
    namespace: str,
    file: UploadFile = File(...),
    visibility: str | None = Form(default=None),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        entries = extract_package(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc

    dry_run, _, resolved_visibility = await publish_entries(request, namespace, entries, mock_user_id, authorization, visibility)

    return ok(
        "response.success.published",
        publish_response(namespace, dry_run.resolved_slug, dry_run.resolved_version, resolved_visibility),
        request,
    )


@router.post("/api/v1/publish")
async def publish_legacy_skill(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = Form(...),
    confirm_warnings: bool = Form(default=False, alias="confirmWarnings"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    _ = confirm_warnings
    normalized_namespace = normalize_namespace(namespace)
    try:
        entries = extract_package(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc

    _, result, _ = await publish_entries(
        request,
        normalized_namespace,
        entries,
        mock_user_id,
        authorization,
        "PUBLIC",
        compat_namespace=normalized_namespace,
    )
    return compat_publish_response(result)


@router.post("/api/v1/skills")
async def publish_clawhub_root_skill(
    request: Request,
    payload: str = Form(...),
    files: list[UploadFile] = File(...),
    confirm_warnings: bool = Form(default=False, alias="confirmWarnings"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    _ = confirm_warnings
    try:
        payload_data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc
    if not isinstance(payload_data, dict):
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid")

    namespace = namespace_from_payload(payload_data)
    entries = await extract_multipart_files(files)
    compat_slug = payload_data.get("slug")
    _, result, _ = await publish_entries(
        request,
        namespace,
        entries,
        mock_user_id,
        authorization,
        "PUBLIC",
        compat_namespace=namespace,
        compat_slug=compat_slug if isinstance(compat_slug, str) else None,
    )
    return compat_publish_response(result)
