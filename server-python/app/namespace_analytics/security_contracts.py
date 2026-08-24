from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SecuritySeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNCLASSIFIED"]


class NamespaceSecuritySeverityCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    info: int
    unclassified: int


class NamespaceSecurityAnalyticsSummary(BaseModel):
    affectedNamespaceCount: int
    affectedSkillCount: int
    affectedVersionCount: int
    findingCount: int
    severityCounts: NamespaceSecuritySeverityCounts


class NamespaceSecurityAnalyticsItem(BaseModel):
    namespaceId: int
    slug: str
    displayName: str
    type: Literal["GLOBAL", "TEAM"]
    status: Literal["ACTIVE", "FROZEN", "ARCHIVED"]
    affectedSkillCount: int
    affectedVersionCount: int
    findingCount: int
    severityCounts: NamespaceSecuritySeverityCounts
    maxSeverity: SecuritySeverity
    latestScanAt: datetime


class NamespaceSecurityAnalyticsData(BaseModel):
    summary: NamespaceSecurityAnalyticsSummary
    items: list[NamespaceSecurityAnalyticsItem]
    page: int
    size: int
    total: int


class NamespaceSecurityAnalyticsEnvelope(BaseModel):
    code: int
    msg: str
    data: NamespaceSecurityAnalyticsData
    timestamp: str
    requestId: str


class NamespaceSecurityVersionItem(BaseModel):
    versionId: int
    version: str
    status: Literal[
        "DRAFT",
        "SCANNING",
        "SCAN_FAILED",
        "UPLOADED",
        "PENDING_REVIEW",
        "PUBLISHED",
        "REJECTED",
        "YANKED",
    ]
    findingCount: int
    severityCounts: NamespaceSecuritySeverityCounts
    maxSeverity: SecuritySeverity
    latestScanAt: datetime
    scannerTypes: list[Literal["skill-scanner", "custom"]]


class NamespaceSecuritySkillItem(BaseModel):
    skillId: int
    slug: str
    displayName: str
    ownerId: str
    ownerDisplayName: str | None
    visibility: Literal["PUBLIC", "NAMESPACE_ONLY", "PRIVATE"]
    status: Literal["ACTIVE", "ARCHIVED"]
    hidden: bool
    affectedVersionCount: int
    findingCount: int
    severityCounts: NamespaceSecuritySeverityCounts
    maxSeverity: SecuritySeverity
    latestScanAt: datetime
    versions: list[NamespaceSecurityVersionItem]


class NamespaceSecuritySkillsData(BaseModel):
    items: list[NamespaceSecuritySkillItem]
    page: int
    size: int
    total: int


class NamespaceSecuritySkillsEnvelope(BaseModel):
    code: int
    msg: str
    data: NamespaceSecuritySkillsData
    timestamp: str
    requestId: str
