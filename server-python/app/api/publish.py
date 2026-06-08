from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile

from app.api.auth import read_current_mock_user
from app.core.config import get_settings
from app.core.response import ok
from app.publish.dry_run import (
    PublishDryRunInput,
    PublishDryRunRepository,
    PublishDryRunResult,
    validate_publish_dry_run,
)
from app.publish.orchestration import PublishWriteInput, PublishWriteResult, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata, extract_package, validate_package
from app.publish.replacement import ReplaceableVersion, find_replaceable_version
from app.publish.scanner_handoff import RedisScanTaskPublisher

router = APIRouter()

VALID_VISIBILITIES = {"PUBLIC", "PRIVATE", "NAMESPACE_ONLY"}


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


async def resolve_current_user(request: Request, mock_user_id: str | None) -> dict[str, object]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    if reader is not None:
        data = reader(user_id)
        if isawaitable(data):
            data = await data
    else:
        data = await read_current_mock_user(request.app.state.db_engine, user_id)

    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(data)


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
    return await validate_publish_dry_run(
        PublishDryRunInput(
            namespace_slug=namespace,
            entries=entries,
            publisher_id=publisher_id,
            visibility=visibility,
            platform_roles=platform_roles,
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
        scan_task_publisher = RedisScanTaskPublisher(settings.redis_url, settings.scan_stream_key)
    return await execute_publish_write(
        request.app.state.db_engine,
        write_input,
        scan_task_publisher=scan_task_publisher,
    )


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
) -> dict[str, Any]:
    user = await resolve_current_user(request, mock_user_id)
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
        {str(role) for role in user.get("platformRoles", [])},
    )
    return ok("response.success.read", dry_run_response(result), request)


@router.post("/api/cli/v1/skills/{namespace}/publish")
async def publish_cli_skill(
    request: Request,
    namespace: str,
    file: UploadFile = File(...),
    visibility: str | None = Form(default=None),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user = await resolve_current_user(request, mock_user_id)
    resolved_visibility = normalize_visibility(visibility)
    platform_roles = {str(role) for role in user.get("platformRoles", [])}
    publisher_id = str(user["userId"])

    try:
        entries = extract_package(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid") from exc

    dry_run = await run_publish_validate(request, namespace, entries, publisher_id, resolved_visibility, platform_roles)
    if not dry_run.valid:
        messages = dry_run.errors or dry_run.warnings
        raise HTTPException(status_code=400, detail=", ".join(messages))
    if dry_run.resolved_slug is None or dry_run.resolved_version is None:
        raise HTTPException(status_code=400, detail="error.skill.publish.package.invalid")

    package_validation = validate_package(entries)
    metadata = package_validation.metadata
    if metadata is None:
        raise HTTPException(status_code=400, detail="error.skill.publish.skillMd.notFound")

    namespace_id = await resolve_namespace_id_for_write(request, namespace, publisher_id, platform_roles)
    settings = getattr(request.app.state, "settings", get_settings())
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
        auto_publish="SUPER_ADMIN" in platform_roles,
        metadata=metadata_with_resolved_version(metadata, dry_run.resolved_version),
        entries=entries,
        storage_base_path=settings.storage_base_path,
        scanner_enabled=settings.security_scanner_enabled,
        scan_mode=settings.security_scanner_mode,
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        replacement=replacement,
    )
    await run_publish_write(request, write_input)

    return ok(
        "response.success.published",
        publish_response(namespace, dry_run.resolved_slug, dry_run.resolved_version, resolved_visibility),
        request,
    )
