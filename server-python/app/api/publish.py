from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile

from app.api.auth import read_current_mock_user
from app.core.response import ok
from app.publish.dry_run import (
    PublishDryRunInput,
    PublishDryRunRepository,
    PublishDryRunResult,
    validate_publish_dry_run,
)
from app.publish.package import PackageEntry, extract_package

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
