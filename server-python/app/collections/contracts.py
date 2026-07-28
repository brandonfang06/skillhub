from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


MAX_COLLECTION_MEMBERS = 100


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CollectionContract(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class CollectionCreateRequest(CollectionContract):
    slug: str
    display_name: str
    summary: str


class CollectionMemberInput(CollectionContract):
    skill_id: int
    skill_version_id: int
    position: int
    note: str | None = None


class CollectionDraftReplaceRequest(CollectionContract):
    display_name: str
    summary: str
    release_notes: str | None = None
    members: list[CollectionMemberInput] = Field(
        default_factory=list,
        max_length=MAX_COLLECTION_MEMBERS,
    )


class CollectionPublishRequest(CollectionContract):
    version: str
    draft_revision: int


class CollectionStatusRequest(CollectionContract):
    status: Literal["ACTIVE", "ARCHIVED"]
    reason: str | None = None


class CollectionMemberResponse(CollectionContract):
    skill_id: int | None
    skill_version_id: int | None
    namespace: str
    skill_slug: str
    version: str
    position: int
    note: str | None = None


class CollectionVersionSummaryResponse(CollectionContract):
    version_id: int
    version: str
    status: Literal["DRAFT", "PUBLISHED", "YANKED"]
    draft_revision: int
    member_count: int
    release_notes: str | None = None
    created_at: str
    published_at: str | None = None


class CollectionVersionResponse(CollectionVersionSummaryResponse):
    members: list[CollectionMemberResponse]


class CollectionSummaryResponse(CollectionContract):
    collection_id: int
    namespace: str
    slug: str
    display_name: str
    summary: str
    status: Literal["ACTIVE", "ARCHIVED"]
    hidden: bool
    can_curate: bool
    latest_published_version: CollectionVersionSummaryResponse | None = None
    draft: CollectionVersionSummaryResponse | None = None
    created_at: str
    updated_at: str


class CollectionListResponse(CollectionContract):
    items: list[CollectionSummaryResponse]
    total: int


class CollectionDetailResponse(CollectionSummaryResponse):
    latest_published_version: CollectionVersionResponse | None = None
    draft: CollectionVersionResponse | None = None


class CollectionResolveMemberResponse(CollectionContract):
    namespace: str
    slug: str
    version: str
    version_id: int
    fingerprint: str
    download_url: str


class CollectionResolveResponse(CollectionContract):
    namespace: str
    slug: str
    version: str
    version_id: int
    members: list[CollectionResolveMemberResponse]


class CollectionDeletedResponse(CollectionContract):
    deleted: bool


DataT = TypeVar("DataT")


class CollectionEnvelope(CollectionContract, Generic[DataT]):
    code: int
    msg: str
    data: DataT
    timestamp: str
    request_id: str


class CollectionListEnvelope(CollectionEnvelope[CollectionListResponse]):
    pass


class CollectionDetailEnvelope(CollectionEnvelope[CollectionDetailResponse]):
    pass


class CollectionVersionEnvelope(CollectionEnvelope[CollectionVersionResponse]):
    pass


class CollectionResolveEnvelope(CollectionEnvelope[CollectionResolveResponse]):
    pass


class CollectionDeletedEnvelope(CollectionEnvelope[CollectionDeletedResponse]):
    pass
