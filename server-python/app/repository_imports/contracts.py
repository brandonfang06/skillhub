from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.collections.contracts import MAX_COLLECTION_MEMBERS


RepositoryImportState = Literal[
    "PREVIEW_READY",
    "INGESTING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
]
RepositoryImportTerminalState = Literal["COMPLETED", "PARTIAL"]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class RepositoryImportContract(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class RepositoryImportPreviewRequest(RepositoryImportContract):
    project_path: str
    ref: str = "main"
    upstream_url: str | None = None


class RepositoryImportCandidateResponse(RepositoryImportContract):
    candidate_id: int
    source_path: str
    detected_name: str
    detected_description: str
    source_version: str | None = None
    target_slug: str | None = None
    target_version: str | None = None
    visibility: str | None = None
    state: Literal["DISCOVERED", "SELECTED", "CREATED", "FAILED"]
    skill_id: int | None = None
    skill_version_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None


class RepositoryImportResponse(RepositoryImportContract):
    import_id: int
    namespace: str
    provider: Literal["GITLAB"] = "GITLAB"
    project_id: str
    project_full_path: str
    requested_ref: str
    resolved_commit_sha: str
    source_web_url: str
    upstream_url: str | None = None
    archive_sha256: str
    archive_bytes: int
    state: RepositoryImportState
    error_code: str | None = None
    previous_import_id: int | None = None
    candidates: list[RepositoryImportCandidateResponse]


class RepositoryImportSelection(RepositoryImportContract):
    candidate_id: int
    target_slug: str
    target_version: str
    visibility: Literal["PUBLIC", "NAMESPACE_ONLY", "PRIVATE"]


class RepositoryImportIngestRequest(RepositoryImportContract):
    candidates: list[RepositoryImportSelection] = Field(min_length=1)


class RepositoryImportCandidateResult(RepositoryImportContract):
    candidate_id: int
    state: Literal["CREATED", "FAILED"]
    skill_id: int | None = None
    skill_version_id: int | None = None
    version_status: str | None = None
    error_code: str | None = None


class RepositoryImportIngestResponse(RepositoryImportContract):
    import_id: int
    state: RepositoryImportTerminalState
    results: list[RepositoryImportCandidateResult]


class RepositoryImportCollectionDraftRequest(RepositoryImportContract):
    collection_slug: str
    display_name: str
    summary: str
    candidate_ids: list[int] = Field(
        min_length=1,
        max_length=MAX_COLLECTION_MEMBERS,
    )


class RepositoryImportCollectionDraftResponse(RepositoryImportContract):
    collection_slug: str
    draft_revision: int
    member_count: int


class RepositoryImportUpdateCheckResponse(RepositoryImportContract):
    previous_import_id: int
    changed: bool
    previous_commit_sha: str
    current_commit_sha: str
    preview: RepositoryImportResponse | None = None


T = TypeVar("T")


class RepositoryImportEnvelope(RepositoryImportContract, Generic[T]):
    code: int
    msg: str
    data: T
    timestamp: str
    request_id: str
