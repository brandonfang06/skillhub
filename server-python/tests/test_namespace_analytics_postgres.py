from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.namespace_analytics.repository import (
    export_namespace_analytics_csv,
    list_namespace_analytics,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_namespace_analytics_executes_nullable_filters_on_postgres() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        result = await list_namespace_analytics(
            engine,
            query=None,
            namespace_type="ALL",
            namespace_status="ACTIVE",
            start_time=None,
            end_time=None,
            source=None,
            sort="periodDownloads",
            direction="desc",
            page=0,
            size=20,
            retention_months=12,
        )
    finally:
        await engine.dispose()

    assert result["page"] == 0
    assert result["size"] == 20
    assert isinstance(result["summary"]["namespaceCount"], int)
    assert isinstance(result["items"], list)


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_namespace_analytics_csv_executes_nullable_filters_on_postgres() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        csv_body, truncated = await export_namespace_analytics_csv(
            engine,
            query=None,
            namespace_type="ALL",
            namespace_status="ACTIVE",
            start_time=None,
            end_time=None,
            source=None,
            sort="periodDownloads",
            direction="desc",
        )
    finally:
        await engine.dispose()

    assert csv_body.startswith("\ufeffnamespace_id,namespace_slug")
    assert isinstance(truncated, bool)
