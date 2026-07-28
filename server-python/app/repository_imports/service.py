from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
import re
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.collections.contracts import MAX_COLLECTION_MEMBERS
from app.repository_imports.archive import (
    RepositoryArchiveLimits,
    read_repository_archive,
)
from app.repository_imports.contracts import RepositoryImportSelection
from app.repository_imports.discovery import RepositorySkillCandidate, discover_skill_candidates
from app.repository_imports.gitlab_client import (
    GitLabImportClient,
    GitLabPreviewSource,
)
from app.repository_imports.repository import (
    RepositoryImportRepository,
    repository_import_repository,
)


class RepositoryImportServiceError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


class RepositoryImportCandidatePublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepositoryImportContext:
    actor_user_id: str
    platform_roles: list[str]
    request_id: str | None
    client_ip: str | None
    user_agent: str | None
    archive_limits: RepositoryArchiveLimits = field(
        default_factory=RepositoryArchiveLimits
    )
    import_max_candidates: int = 100


@dataclass(frozen=True)
class ImportedSkillResult:
    skill_id: int
    version_id: int
    version_status: str


ImportPublisher = Callable[
    [
        dict[str, Any],
        RepositorySkillCandidate,
        RepositoryImportSelection,
        RepositoryImportContext,
    ],
    Awaitable[ImportedSkillResult],
]
CollectionSeeder = Callable[
    [dict[str, Any], list[dict[str, Any]], Any, RepositoryImportContext],
    Awaitable[dict[str, Any]],
]

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


async def _read_repository_archive(
    archive: bytes,
    context: RepositoryImportContext,
):
    return await asyncio.to_thread(
        read_repository_archive,
        archive,
        context.archive_limits,
    )


def _require_candidate_limit(
    candidates: list[RepositorySkillCandidate],
    context: RepositoryImportContext,
) -> None:
    if len(candidates) > context.import_max_candidates:
        raise RepositoryImportServiceError(
            "error.repositoryImport.candidate.tooMany",
            status_code=413,
        )


async def preview_repository_import(
    engine: Any,
    *,
    namespace: str,
    project_path: str,
    requested_ref: str,
    upstream_url: str | None,
    context: RepositoryImportContext,
    client: GitLabImportClient,
    repository: RepositoryImportRepository = repository_import_repository,
) -> dict[str, Any]:
    namespace_row = await repository.authorize_namespace(
        engine,
        namespace=namespace,
        actor_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
    )
    source = await client.preview_source(project_path, requested_ref)
    files = await _read_repository_archive(source.archive, context)
    candidates = discover_skill_candidates(files)
    _require_candidate_limit(candidates, context)
    return await repository.create_preview(
        engine,
        namespace_row=namespace_row,
        actor_user_id=context.actor_user_id,
        source=source,
        upstream_url=upstream_url,
        candidates=candidates,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )


def _validate_selection(selection: RepositoryImportSelection) -> None:
    if (
        len(selection.target_slug) > 128
        or SLUG_PATTERN.fullmatch(selection.target_slug) is None
        or "--" in selection.target_slug
    ):
        raise RepositoryImportServiceError(
            "error.repositoryImport.targetSlug.invalid"
        )
    if VERSION_PATTERN.fullmatch(selection.target_version) is None:
        raise RepositoryImportServiceError(
            "error.repositoryImport.targetVersion.invalid"
        )


async def ingest_repository_import(
    engine: Any,
    *,
    import_id: int,
    selections: list[RepositoryImportSelection],
    context: RepositoryImportContext,
    client: GitLabImportClient,
    publisher: ImportPublisher,
    repository: RepositoryImportRepository = repository_import_repository,
) -> dict[str, Any]:
    import_row = await repository.read_authorized_import(
        engine,
        import_id=import_id,
        actor_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
    )
    import_state = str(import_row["state"])
    if import_state != "PREVIEW_READY":
        detail = (
            "error.repositoryImport.ingest.inProgress"
            if import_state == "INGESTING"
            else "error.repositoryImport.ingest.notAvailable"
        )
        raise RepositoryImportServiceError(detail, status_code=409)

    seen: set[int] = set()
    for selection in selections:
        _validate_selection(selection)
        if selection.candidate_id in seen:
            raise RepositoryImportServiceError(
                "error.repositoryImport.candidate.duplicate"
            )
        seen.add(selection.candidate_id)

    candidate_rows = await repository.read_candidates(engine, import_id)
    by_id = {int(row["candidate_id"]): row for row in candidate_rows}
    for selection in selections:
        if selection.candidate_id not in by_id:
            raise RepositoryImportServiceError(
                "error.repositoryImport.candidate.notFound",
                status_code=404,
            )

    operation_id = uuid4().hex
    claimed = await repository.claim_ingest(
        engine,
        import_id=import_id,
        operation_id=operation_id,
        actor_user_id=context.actor_user_id,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
    if not claimed:
        raise RepositoryImportServiceError(
            "error.repositoryImport.ingest.inProgress",
            status_code=409,
        )

    source = await client.download_archive(
        str(import_row["project_full_path"]),
        str(import_row["resolved_commit_sha"]),
    )
    if sha256(source).hexdigest() != str(import_row["archive_sha256"]):
        raise RepositoryImportServiceError(
            "error.repositoryImport.archive.changed",
            status_code=409,
        )
    archive_files = await _read_repository_archive(source, context)
    candidates = discover_skill_candidates(archive_files)
    _require_candidate_limit(candidates, context)
    discovered = {
        candidate.source_path: candidate
        for candidate in candidates
    }

    results: list[dict[str, Any]] = []
    had_failure = False
    for selection in selections:
        row = by_id[selection.candidate_id]
        if row.get("state") == "CREATED":
            results.append(
                {
                    "candidate_id": selection.candidate_id,
                    "state": "CREATED",
                    "skill_id": row.get("skill_id"),
                    "skill_version_id": row.get("skill_version_id"),
                    "version_status": row.get("version_status"),
                }
            )
            continue
        candidate = discovered.get(str(row["source_path"]))
        if candidate is None:
            raise RepositoryImportServiceError(
                "error.repositoryImport.candidate.archiveMismatch",
                status_code=409,
            )
        selected = await repository.mark_candidate_selected(
            engine,
            candidate_id=selection.candidate_id,
            operation_id=operation_id,
            target_slug=selection.target_slug,
            target_version=selection.target_version,
            visibility=selection.visibility,
        )
        if not selected:
            raise RepositoryImportServiceError(
                "error.repositoryImport.ingest.ownershipLost",
                status_code=409,
            )
        try:
            published = await publisher(
                import_row,
                candidate,
                selection,
                context,
            )
        except RepositoryImportCandidatePublishError:
            had_failure = True
            error_code = "error.repositoryImport.publishFailed"
            recorded = await repository.mark_candidate_result(
                engine,
                candidate_id=selection.candidate_id,
                operation_id=operation_id,
                skill_id=None,
                skill_version_id=None,
                error_code=error_code,
            )
            if not recorded:
                raise RepositoryImportServiceError(
                    "error.repositoryImport.ingest.ownershipLost",
                    status_code=409,
                )
            results.append(
                {
                    "candidate_id": selection.candidate_id,
                    "state": "FAILED",
                    "error_code": error_code,
                }
            )
            continue
        recorded = await repository.mark_candidate_result(
            engine,
            candidate_id=selection.candidate_id,
            operation_id=operation_id,
            skill_id=published.skill_id,
            skill_version_id=published.version_id,
            error_code=None,
        )
        if not recorded:
            raise RepositoryImportServiceError(
                "error.repositoryImport.ingest.ownershipLost",
                status_code=409,
            )
        row.update(
            {
                "state": "CREATED",
                "skill_id": published.skill_id,
                "skill_version_id": published.version_id,
                "version_status": published.version_status,
            }
        )
        results.append(
            {
                "candidate_id": selection.candidate_id,
                "state": "CREATED",
                "skill_id": published.skill_id,
                "skill_version_id": published.version_id,
                "version_status": published.version_status,
            }
        )
    state = "PARTIAL" if had_failure else "COMPLETED"
    completed = await repository.complete_ingest(
        engine,
        import_id=import_id,
        operation_id=operation_id,
        state=state,
        error_code=None,
        actor_user_id=context.actor_user_id,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
    if not completed:
        raise RepositoryImportServiceError(
            "error.repositoryImport.ingest.ownershipLost",
            status_code=409,
        )
    return {"import_id": import_id, "state": state, "results": results}


async def check_repository_import_updates(
    engine: Any,
    *,
    import_id: int,
    context: RepositoryImportContext,
    client: GitLabImportClient,
    repository: RepositoryImportRepository = repository_import_repository,
) -> dict[str, Any]:
    import_row = await repository.read_authorized_import(
        engine,
        import_id=import_id,
        actor_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
    )
    previous_sha = str(import_row["resolved_commit_sha"])
    resolved = await client.resolve_ref(
        str(import_row["project_full_path"]),
        str(import_row["requested_ref"]),
    )
    if resolved.commit_sha == previous_sha:
        return {
            "previous_import_id": import_id,
            "changed": False,
            "previous_commit_sha": previous_sha,
            "current_commit_sha": resolved.commit_sha,
            "preview": None,
        }

    archive = await client.download_archive(
        resolved.project_full_path,
        resolved.commit_sha,
    )
    source = GitLabPreviewSource(
        project_id=resolved.project_id,
        project_full_path=resolved.project_full_path,
        requested_ref=resolved.requested_ref,
        commit_sha=resolved.commit_sha,
        source_web_url=resolved.source_web_url,
        archive=archive,
        archive_sha256=sha256(archive).hexdigest(),
    )
    files = await _read_repository_archive(archive, context)
    candidates = discover_skill_candidates(files)
    _require_candidate_limit(candidates, context)
    preview = await repository.create_preview(
        engine,
        namespace_row={
            "id": int(import_row["namespace_id"]),
            "slug": str(import_row["namespace"]),
        },
        actor_user_id=context.actor_user_id,
        source=source,
        upstream_url=import_row.get("upstream_url"),
        candidates=candidates,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
        previous_import_id=import_id,
    )
    return {
        "previous_import_id": import_id,
        "changed": True,
        "previous_commit_sha": previous_sha,
        "current_commit_sha": resolved.commit_sha,
        "preview": preview,
    }


async def seed_repository_import_collection_draft(
    engine: Any,
    *,
    import_id: int,
    candidate_ids: list[int],
    payload: Any,
    context: RepositoryImportContext,
    seeder: CollectionSeeder,
    repository: RepositoryImportRepository = repository_import_repository,
) -> dict[str, Any]:
    if len(candidate_ids) > MAX_COLLECTION_MEMBERS:
        raise RepositoryImportServiceError(
            "error.repositoryImport.collectionDraft.tooManyMembers",
            status_code=413,
        )
    import_row = await repository.read_authorized_import(
        engine,
        import_id=import_id,
        actor_user_id=context.actor_user_id,
        platform_roles=context.platform_roles,
    )
    members = await repository.read_published_members(
        engine,
        import_id=import_id,
        candidate_ids=candidate_ids,
    )
    if len(members) != len(set(candidate_ids)):
        raise RepositoryImportServiceError(
            "error.repositoryImport.collectionDraft.publishedRequired",
            status_code=409,
        )
    return await seeder(import_row, members, payload, context)
