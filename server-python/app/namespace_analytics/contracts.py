from __future__ import annotations

from datetime import datetime

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
    source: str | None
    retentionMonths: int


class NamespaceAnalyticsItem(BaseModel):
    namespaceId: int
    slug: str
    displayName: str
    type: str
    status: str
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
