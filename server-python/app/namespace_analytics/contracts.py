from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NamespaceAnalyticsSummary(BaseModel):
    namespaceCount: int
    maintainerCount: int
    skillCount: int
    lifetimeDownloads: int
    periodDownloads: int


class NamespaceAnalyticsPeriod(BaseModel):
    startTime: datetime
    endTime: datetime
    source: Literal["web", "cli", "api"] | None
    retentionMonths: int


class NamespaceAnalyticsItem(BaseModel):
    namespaceId: int
    slug: str
    displayName: str
    type: Literal["GLOBAL", "TEAM"]
    status: Literal["ACTIVE", "FROZEN", "ARCHIVED"]
    maintainerCount: int
    skillCount: int
    lifetimeDownloads: int
    periodDownloads: int


class NamespaceAnalyticsData(BaseModel):
    summary: NamespaceAnalyticsSummary
    period: NamespaceAnalyticsPeriod
    items: list[NamespaceAnalyticsItem]
    page: int
    size: int
    total: int


class NamespaceAnalyticsEnvelope(BaseModel):
    code: int
    msg: str
    data: NamespaceAnalyticsData
    timestamp: str
    requestId: str
