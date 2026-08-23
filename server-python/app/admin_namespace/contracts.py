from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NamespaceStatus = Literal["ACTIVE", "FROZEN", "ARCHIVED"]
NamespaceType = Literal["TEAM", "GLOBAL"]
NamespaceRole = Literal["OWNER", "ADMIN", "MEMBER"]
ManageableNamespaceRole = Literal["ADMIN", "MEMBER"]


class AdminNamespaceStats(BaseModel):
    memberCount: int
    skillCount: int


class AdminNamespacePermissions(BaseModel):
    currentUserRole: NamespaceRole | None
    platformOverride: bool
    immutable: bool
    canManageMembers: bool
    canGovernNamespace: bool
    canPublish: bool
    canTransferOwnership: bool
    canFreeze: bool
    canUnfreeze: bool
    canArchive: bool
    canRestore: bool


class AdminNamespaceSummary(BaseModel):
    id: int
    slug: str
    displayName: str
    status: NamespaceStatus
    description: str | None
    type: NamespaceType
    avatarUrl: str | None
    createdBy: str | None
    createdAt: datetime
    updatedAt: datetime
    stats: AdminNamespaceStats
    permissions: AdminNamespacePermissions


class AdminNamespaceListStats(BaseModel):
    total: int
    active: int
    frozen: int
    archived: int


class AdminNamespaceListData(BaseModel):
    items: list[AdminNamespaceSummary]
    total: int
    page: int
    size: int
    stats: AdminNamespaceListStats


class AdminNamespaceMember(BaseModel):
    id: int
    namespaceId: int
    userId: str
    displayName: str | None
    email: str | None
    role: NamespaceRole
    createdAt: datetime
    updatedAt: datetime


class AdminNamespaceMemberPage(BaseModel):
    items: list[AdminNamespaceMember]
    total: int
    page: int
    size: int


class AdminNamespaceCandidate(BaseModel):
    userId: str
    displayName: str
    email: str | None
    status: Literal["ACTIVE"]


class AdminNamespaceListEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceListData
    timestamp: str
    requestId: str


class AdminNamespaceDetailEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceSummary
    timestamp: str
    requestId: str


class AdminNamespaceMemberPageEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceMemberPage
    timestamp: str
    requestId: str


class AdminNamespaceCandidateListEnvelope(BaseModel):
    code: int
    msg: str
    data: list[AdminNamespaceCandidate]
    timestamp: str
    requestId: str


class AdminNamespaceMemberRequest(BaseModel):
    userId: str = Field(min_length=1, max_length=128)
    role: ManageableNamespaceRole

    @field_validator("userId")
    @classmethod
    def user_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("userId must not be blank")
        return value


class AdminNamespaceBatchMemberRequest(BaseModel):
    members: list[AdminNamespaceMemberRequest] = Field(min_length=1)


class AdminNamespaceUpdateMemberRoleRequest(BaseModel):
    role: ManageableNamespaceRole


class AdminNamespaceTransferOwnershipRequest(BaseModel):
    newOwnerId: str = Field(min_length=1, max_length=128)

    @field_validator("newOwnerId")
    @classmethod
    def new_owner_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("newOwnerId must not be blank")
        return value


class AdminNamespaceLifecycleRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class AdminNamespaceMessage(BaseModel):
    message: str


class AdminNamespaceBatchMemberResult(BaseModel):
    userId: str
    role: NamespaceRole
    success: bool
    error: str | None


class AdminNamespaceBatchMemberData(BaseModel):
    totalCount: int
    successCount: int
    failureCount: int
    results: list[AdminNamespaceBatchMemberResult]


class AdminNamespaceMemberEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceMember
    timestamp: str
    requestId: str


class AdminNamespaceBatchMemberEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceBatchMemberData
    timestamp: str
    requestId: str


class AdminNamespaceMessageEnvelope(BaseModel):
    code: int
    msg: str
    data: AdminNamespaceMessage
    timestamp: str
    requestId: str
