from __future__ import annotations

from inspect import isawaitable
from typing import Any, Awaitable

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.auth.context import resolve_current_user_or_401
from app.auth.policy import (
    platform_roles,
    reject_api_token_principal_for_route,
)
from app.collections.contracts import (
    CollectionDraftReplaceRequest,
    CollectionMemberInput,
)
from app.collections.read_repository import get_collection as read_collection_detail
from app.collections.service import (
    CollectionMutationError,
    MutationContext,
    create_collection_draft,
    replace_collection_draft,
)
from app.core.config import get_settings
from app.core.response import ok
from app.object_storage import object_storage_for_settings
from app.publish.orchestration import PublishWriteInput
from app.publish.package import SkillMetadata, validate_package
from app.repository_imports.contracts import (
    RepositoryImportCollectionDraftRequest,
    RepositoryImportCollectionDraftResponse,
    RepositoryImportEnvelope,
    RepositoryImportIngestRequest,
    RepositoryImportIngestResponse,
    RepositoryImportPreviewRequest,
    RepositoryImportResponse,
    RepositoryImportUpdateCheckResponse,
)
from app.repository_imports.gitlab_client import (
    GitLabClientConfig,
    GitLabImportClient,
)
from app.repository_imports.archive import RepositoryArchiveLimits
from app.repository_imports.service import (
    ImportedSkillResult,
    RepositoryImportCandidatePublishError,
    RepositoryImportContext,
    check_repository_import_updates,
    ingest_repository_import,
    preview_repository_import,
    seed_repository_import_collection_draft,
)


def _require_gitlab_import_enabled(request: Request) -> None:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if not (
        bool(getattr(settings, "collections_enabled", False))
        and bool(getattr(settings, "gitlab_import_enabled", False))
    ):
        raise HTTPException(
            status_code=404,
            detail="error.repositoryImport.notFound",
        )


router = APIRouter(dependencies=[Depends(_require_gitlab_import_enabled)])


async def _resolve(result: Any | Awaitable[Any]) -> Any:
    return await result if isawaitable(result) else result


def _raise_import_http(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    detail = str(exc)
    if not (
        detail.startswith("error.repositoryImport.")
        or detail.startswith("error.collection.")
    ):
        detail = "error.repositoryImport.failed"
    raise HTTPException(
        status_code=int(getattr(exc, "status_code", 400)),
        detail=detail,
    ) from exc


async def _current_web_user(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    user = dict(
        await resolve_current_user_or_401(
            request,
            mock_user_id,
            authorization,
        )
    )
    reject_api_token_principal_for_route(user, request.url.path)
    return user


def _context(request: Request, user: dict[str, Any]) -> RepositoryImportContext:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    return RepositoryImportContext(
        actor_user_id=str(user["userId"]),
        platform_roles=platform_roles(user),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        archive_limits=RepositoryArchiveLimits(
            max_file_count=int(
                getattr(settings, "gitlab_archive_max_files", 500)
            ),
            max_single_file_bytes=int(
                getattr(
                    settings,
                    "gitlab_archive_max_single_file_bytes",
                    5 * 1024 * 1024,
                )
            ),
            max_total_bytes=int(
                getattr(
                    settings,
                    "gitlab_archive_max_expanded_bytes",
                    50 * 1024 * 1024,
                )
            ),
        ),
        import_max_candidates=int(
            getattr(settings, "gitlab_import_max_candidates", 100)
        ),
    )


def _client(request: Request) -> GitLabImportClient:
    injected = getattr(request.app.state, "gitlab_import_client", None)
    if injected is not None:
        return injected
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if (
        not getattr(settings, "gitlab_base_url", "")
        or not getattr(settings, "gitlab_token", "")
        or not getattr(settings, "gitlab_allowed_groups", [])
    ):
        raise HTTPException(
            status_code=503,
            detail="error.repositoryImport.gitlab.notConfigured",
        )
    return GitLabImportClient(
        GitLabClientConfig(
            base_url=settings.gitlab_base_url,
            token=settings.gitlab_token,
            allowed_groups=tuple(settings.gitlab_allowed_groups),
            connect_timeout_ms=settings.gitlab_connect_timeout_ms,
            read_timeout_ms=settings.gitlab_read_timeout_ms,
            archive_max_bytes=settings.gitlab_archive_max_bytes,
            ca_bundle_path=settings.gitlab_ca_bundle_path,
        )
    )


async def _publish_candidate(
    request: Request,
    import_row: dict[str, Any],
    candidate: Any,
    selection: Any,
    context: RepositoryImportContext,
) -> ImportedSkillResult:
    validation = validate_package(candidate.entries)
    if not validation.valid or validation.metadata is None:
        raise RepositoryImportCandidatePublishError(
            "error.repositoryImport.discovery.package.invalid"
        )
    metadata = SkillMetadata(
        name=validation.metadata.name,
        description=validation.metadata.description,
        version=selection.target_version,
        frontmatter={
            **validation.metadata.frontmatter,
            "version": selection.target_version,
        },
    )
    settings = getattr(request.app.state, "settings", None) or get_settings()
    write_input = PublishWriteInput(
        namespace_id=int(import_row["namespace_id"]),
        namespace_slug=str(import_row["namespace"]),
        slug=selection.target_slug,
        display_name=metadata.name,
        summary=metadata.description,
        publisher_id=context.actor_user_id,
        visibility=selection.visibility,
        version=selection.target_version,
        auto_publish="SUPER_ADMIN" in set(context.platform_roles),
        metadata=metadata,
        entries=candidate.entries,
        storage_base_path=settings.storage_base_path,
        storage=object_storage_for_settings(settings),
        scanner_enabled=settings.security_scanner_enabled,
        scan_mode=settings.security_scanner_mode,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
    injected = getattr(request.app.state, "repository_import_publish_writer", None)
    if injected is not None:
        result = await _resolve(injected(write_input))
    else:
        from app.api.publish import run_publish_write

        result = await run_publish_write(request, write_input)
    return ImportedSkillResult(
        skill_id=int(result.skill_id),
        version_id=int(result.version_id),
        version_status=str(result.version_status),
    )


async def _seed_collection(
    request: Request,
    import_row: dict[str, Any],
    members: list[dict[str, Any]],
    payload: RepositoryImportCollectionDraftRequest,
    context: RepositoryImportContext,
) -> dict[str, Any]:
    mutation_context = MutationContext(
        actor_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
    detail = await read_collection_detail(
        request.app.state.db_engine,
        namespace=str(import_row["namespace"]),
        collection=payload.collection_slug,
        current_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
    )
    if detail.get("draft") is None:
        await create_collection_draft(
            request.app.state.db_engine,
            namespace=str(import_row["namespace"]),
            collection=payload.collection_slug,
            context=mutation_context,
        )
        detail = await read_collection_detail(
            request.app.state.db_engine,
            namespace=str(import_row["namespace"]),
            collection=payload.collection_slug,
            current_user_id=context.actor_user_id,
            platform_roles=context.platform_roles,
        )
    revision = int(detail["draft"]["draftRevision"])
    version = await replace_collection_draft(
        request.app.state.db_engine,
        namespace=str(import_row["namespace"]),
        collection=payload.collection_slug,
        payload=CollectionDraftReplaceRequest(
            display_name=payload.display_name,
            summary=payload.summary,
            members=[
                CollectionMemberInput(
                    skill_id=int(member["skill_id"]),
                    skill_version_id=int(member["skill_version_id"]),
                    position=position,
                )
                for position, member in enumerate(members)
            ],
        ),
        expected_revision=revision,
        context=mutation_context,
    )
    return {
        "collection_slug": payload.collection_slug,
        "draft_revision": int(version["draftRevision"]),
        "member_count": len(members),
    }


@router.post(
    "/api/web/namespaces/{namespace}/repository-imports/preview",
    response_model=RepositoryImportEnvelope[RepositoryImportResponse],
)
async def preview_repository_import_route(
    request: Request,
    namespace: str,
    payload: RepositoryImportPreviewRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        writer = getattr(
            request.app.state,
            "repository_import_preview_writer",
            None,
        )
        data = await _resolve(
            writer(namespace, payload, user, request)
            if writer is not None
            else preview_repository_import(
                request.app.state.db_engine,
                namespace=namespace,
                project_path=payload.project_path,
                requested_ref=payload.ref,
                upstream_url=payload.upstream_url,
                context=_context(request, user),
                client=_client(request),
            )
        )
    except Exception as exc:
        _raise_import_http(exc)
    return ok("repositoryImport.preview.ready", data, request)


@router.post(
    "/api/web/repository-imports/{import_id}/ingest",
    response_model=RepositoryImportEnvelope[RepositoryImportIngestResponse],
)
async def ingest_repository_import_route(
    request: Request,
    import_id: int,
    payload: RepositoryImportIngestRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        writer = getattr(
            request.app.state,
            "repository_import_ingest_writer",
            None,
        )

        async def publisher(import_row, candidate, selection, context):
            return await _publish_candidate(
                request,
                import_row,
                candidate,
                selection,
                context,
            )

        data = await _resolve(
            writer(import_id, payload, user, request)
            if writer is not None
            else ingest_repository_import(
                request.app.state.db_engine,
                import_id=import_id,
                selections=payload.candidates,
                context=_context(request, user),
                client=_client(request),
                publisher=publisher,
            )
        )
    except Exception as exc:
        _raise_import_http(exc)
    return ok("repositoryImport.ingest.completed", data, request)


@router.post(
    "/api/web/repository-imports/{import_id}/check-updates",
    response_model=RepositoryImportEnvelope[
        RepositoryImportUpdateCheckResponse
    ],
)
async def check_repository_import_updates_route(
    request: Request,
    import_id: int,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        writer = getattr(
            request.app.state,
            "repository_import_update_writer",
            None,
        )
        data = await _resolve(
            writer(import_id, user, request)
            if writer is not None
            else check_repository_import_updates(
                request.app.state.db_engine,
                import_id=import_id,
                context=_context(request, user),
                client=_client(request),
            )
        )
    except Exception as exc:
        _raise_import_http(exc)
    return ok("repositoryImport.update.checked", data, request)


@router.post(
    "/api/web/repository-imports/{import_id}/collection-draft",
    response_model=RepositoryImportEnvelope[
        RepositoryImportCollectionDraftResponse
    ],
)
async def seed_repository_import_collection_route(
    request: Request,
    import_id: int,
    payload: RepositoryImportCollectionDraftRequest,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    user = await _current_web_user(request, x_mock_user_id, authorization)
    try:
        writer = getattr(
            request.app.state,
            "repository_import_collection_writer",
            None,
        )

        async def seeder(import_row, members, seed_payload, context):
            return await _seed_collection(
                request,
                import_row,
                members,
                seed_payload,
                context,
            )

        data = await _resolve(
            writer(import_id, payload, user, request)
            if writer is not None
            else seed_repository_import_collection_draft(
                request.app.state.db_engine,
                import_id=import_id,
                candidate_ids=payload.candidate_ids,
                payload=payload,
                context=_context(request, user),
                seeder=seeder,
            )
        )
    except Exception as exc:
        _raise_import_http(exc)
    return ok("repositoryImport.collectionDraft.ready", data, request)
