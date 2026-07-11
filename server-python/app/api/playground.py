from functools import partial
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import bearer_token, resolve_current_user_or_401
from app.playground.capability import (
    CapabilityError,
    issue_capability,
    verify_capability,
)
from app.playground.context import build_context_bundle
from app.playground.contracts import (
    CapabilityRequest,
    CapabilityResponse,
    PlaygroundContextResponse,
)
from app.skills.read_files import SkillResolveError
from app.skills.read_repository import (
    read_skill_detail,
    read_skill_version_detail,
    read_skill_version_file_content,
    read_skill_version_files,
)


router = APIRouter(tags=["Playground"])


async def _resolve(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


@router.post(
    "/api/web/skills/{namespace}/{slug}/playground-capability",
    response_model=CapabilityResponse,
)
async def create_playground_capability(
    namespace: str,
    slug: str,
    payload: CapabilityRequest,
    request: Request,
    mock_user_id: str | None = Header(
        default=None,
        alias="X-Mock-User-Id",
    ),
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> CapabilityResponse:
    settings = request.app.state.settings
    if not settings.playground_token_secret:
        raise HTTPException(status_code=503, detail="playground_disabled")

    user = await resolve_current_user_or_401(
        request,
        mock_user_id,
        authorization,
    )
    user_id = str(user["userId"])
    reader = getattr(request.app.state, "playground_version_reader", None)
    try:
        if reader is not None:
            await _resolve(reader(namespace, slug, payload.version, user_id))
        else:
            await read_skill_version_detail(
                request.app.state.db_engine,
                namespace,
                slug,
                payload.version,
                user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    token = issue_capability(
        secret=settings.playground_token_secret,
        issuer=settings.playground_token_issuer,
        audience=settings.playground_token_audience,
        subject=user_id,
        namespace=namespace,
        slug=slug,
        version=payload.version,
        ttl_seconds=settings.playground_token_ttl_seconds,
    )
    claims = verify_capability(
        token,
        secret=settings.playground_token_secret,
        issuer=settings.playground_token_issuer,
        audience=settings.playground_token_audience,
    )
    return CapabilityResponse(
        token=token,
        expires_at=int(claims["exp"]),
    )


@router.get(
    "/api/web/playground/context",
    response_model=PlaygroundContextResponse,
)
async def get_playground_context(
    request: Request,
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
) -> PlaygroundContextResponse:
    settings = request.app.state.settings
    token = bearer_token(authorization)
    if token is None or not settings.playground_token_secret:
        raise HTTPException(
            status_code=401,
            detail="invalid_playground_capability",
        )
    try:
        claims = verify_capability(
            token,
            secret=settings.playground_token_secret,
            issuer=settings.playground_token_issuer,
            audience=settings.playground_token_audience,
        )
    except CapabilityError as exc:
        raise HTTPException(
            status_code=401,
            detail="invalid_playground_capability",
        ) from exc

    reader = getattr(request.app.state, "playground_context_reader", None)
    if reader is not None:
        return PlaygroundContextResponse.model_validate(
            await _resolve(reader(claims))
        )

    try:
        return await build_context_bundle(
            namespace=str(claims["namespace"]),
            slug=str(claims["slug"]),
            version=str(claims["version"]),
            current_user_id=str(claims["sub"]),
            read_detail=partial(
                read_skill_detail,
                request.app.state.db_engine,
            ),
            read_files=partial(
                read_skill_version_files,
                request.app.state.db_engine,
            ),
            read_content=partial(
                read_skill_version_file_content,
                request.app.state.db_engine,
                settings.storage_base_path,
            ),
            max_bytes=settings.playground_context_max_bytes,
        )
    except SkillResolveError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=413,
            detail="playground_context_too_large",
        ) from exc
