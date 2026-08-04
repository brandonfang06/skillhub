from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.namespace_analytics import repository as namespace_repository
from app.namespace_analytics.repository import NamespaceAnalyticsError, resolve_period


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one(self) -> dict[str, Any]:
        assert len(self.rows) == 1
        return self.rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeNamespaceAnalyticsConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any]) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)
        if "namespace-analytics-summary" in sql:
            return FakeResult(
                [
                    {
                        "namespace_count": 2,
                        "maintainer_count": 3,
                        "skill_count": 5,
                        "lifetime_downloads": 120,
                        "period_downloads": 18,
                    }
                ]
            )
        if "namespace-analytics-items" in sql:
            return FakeResult(
                [
                    {
                        "namespace_id": 1,
                        "slug": "global",
                        "display_name": "Global",
                        "type": "GLOBAL",
                        "status": "ACTIVE",
                        "maintainer_count": 2,
                        "skill_count": 3,
                        "lifetime_downloads": 80,
                        "period_downloads": 12,
                    },
                    {
                        "namespace_id": 2,
                        "slug": "platform-tools",
                        "display_name": "Platform Tools",
                        "type": "TEAM",
                        "status": "ACTIVE",
                        "maintainer_count": 1,
                        "skill_count": 2,
                        "lifetime_downloads": 40,
                        "period_downloads": 6,
                    },
                ]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


class FakeConnectionContext:
    def __init__(self, connection: FakeNamespaceAnalyticsConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeNamespaceAnalyticsConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeNamespaceAnalyticsEngine:
    def __init__(self, connection: FakeNamespaceAnalyticsConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.connection)


def test_resolve_period_defaults_to_previous_thirty_days() -> None:
    resolved = resolve_period(None, None, now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 5, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 4, tzinfo=UTC)


def test_resolve_period_uses_end_time_as_default_window_anchor() -> None:
    resolved = resolve_period(None, "2026-08-01T12:30:00Z", now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 2, 12, 30, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 1, 12, 30, tzinfo=UTC)


def test_resolve_period_uses_now_when_only_start_time_is_supplied() -> None:
    resolved = resolve_period("2026-07-20T00:00:00Z", None, now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 20, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 4, tzinfo=UTC)


def test_resolve_period_rejects_reversed_range() -> None:
    with pytest.raises(NamespaceAnalyticsError, match="error.namespaceAnalytics.invalidTimeRange") as invalid:
        resolve_period("2026-08-04T00:00:00Z", "2026-08-03T00:00:00Z")

    assert invalid.value.status_code == 400


@pytest.mark.anyio
async def test_list_namespace_analytics_projects_summary_period_and_rows() -> None:
    connection = FakeNamespaceAnalyticsConnection()

    result = await namespace_repository.list_namespace_analytics(
        FakeNamespaceAnalyticsEngine(connection),
        query=" platform ",
        namespace_type="ALL",
        namespace_status="ACTIVE",
        start_time="2026-07-05T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        source="WEB",
        sort="periodDownloads",
        direction="desc",
        page=0,
        size=20,
        retention_months=12,
    )

    assert result == {
        "summary": {
            "namespaceCount": 2,
            "maintainerCount": 3,
            "skillCount": 5,
            "lifetimeDownloads": 120,
            "periodDownloads": 18,
        },
        "period": {
            "startTime": datetime(2026, 7, 5, tzinfo=UTC),
            "endTime": datetime(2026, 8, 4, tzinfo=UTC),
            "source": "web",
            "retentionMonths": 12,
        },
        "items": [
            {
                "namespaceId": 1,
                "slug": "global",
                "displayName": "Global",
                "type": "GLOBAL",
                "status": "ACTIVE",
                "maintainerCount": 2,
                "skillCount": 3,
                "lifetimeDownloads": 80,
                "periodDownloads": 12,
            },
            {
                "namespaceId": 2,
                "slug": "platform-tools",
                "displayName": "Platform Tools",
                "type": "TEAM",
                "status": "ACTIVE",
                "maintainerCount": 1,
                "skillCount": 2,
                "lifetimeDownloads": 40,
                "periodDownloads": 6,
            },
        ],
        "page": 0,
        "size": 20,
        "total": 2,
    }
    assert connection.params[0]["query"] == "%platform%"
    assert connection.params[0]["source"] == "web"
    assert connection.params[1]["limit"] == 20
    assert connection.params[1]["offset"] == 0


@pytest.mark.anyio
async def test_namespace_analytics_sql_uses_one_eligible_skill_population() -> None:
    connection = FakeNamespaceAnalyticsConnection()

    await namespace_repository.list_namespace_analytics(
        FakeNamespaceAnalyticsEngine(connection),
        query=None,
        namespace_type="GLOBAL",
        namespace_status="ALL",
        start_time="2026-07-05T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        source=None,
        sort="skills",
        direction="desc",
        page=1,
        size=50,
        retention_months=12,
    )

    sql = "\n".join(connection.statements)
    assert "s.status = 'ACTIVE'" in sql
    assert "s.hidden = FALSE" in sql
    assert "sv.status = 'PUBLISHED'" in sql
    assert "COUNT(DISTINCT es.owner_id)" in sql
    assert "de.skill_id = es.skill_id" in sql
    assert "de.created_at >= CAST(:start_time AS timestamptz)" in sql
    assert "de.created_at <= CAST(:end_time AS timestamptz)" in sql
    assert "LEFT JOIN eligible_skills" in sql
    assert connection.params[1]["namespace_type"] == "GLOBAL"
    assert connection.params[1]["namespace_status"] is None
    assert connection.params[1]["limit"] == 50
    assert connection.params[1]["offset"] == 50


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sort", "direction", "expected_order"),
    [
        ("namespace", "asc", "display_name ASC"),
        ("maintainers", "desc", "maintainer_count DESC"),
        ("skills", "desc", "skill_count DESC"),
        ("lifetimeDownloads", "desc", "lifetime_downloads DESC"),
        ("periodDownloads", "desc", "period_downloads DESC"),
    ],
)
async def test_namespace_analytics_uses_allowlisted_sorting(
    sort: str,
    direction: str,
    expected_order: str,
) -> None:
    connection = FakeNamespaceAnalyticsConnection()

    await namespace_repository.list_namespace_analytics(
        FakeNamespaceAnalyticsEngine(connection),
        query=None,
        namespace_type="ALL",
        namespace_status="ACTIVE",
        start_time=None,
        end_time=None,
        source=None,
        sort=sort,
        direction=direction,
        page=0,
        size=20,
        retention_months=12,
        now=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert expected_order in connection.statements[1]
    assert "slug ASC" in connection.statements[1]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespace_type", "PERSONAL"),
        ("namespace_status", "DELETED"),
        ("source", "mobile"),
        ("sort", "drop table skill"),
        ("direction", "sideways"),
    ],
)
async def test_namespace_analytics_rejects_invalid_enum_values(field: str, value: str) -> None:
    params: dict[str, Any] = {
        "query": None,
        "namespace_type": "ALL",
        "namespace_status": "ACTIVE",
        "start_time": None,
        "end_time": None,
        "source": None,
        "sort": "periodDownloads",
        "direction": "desc",
        "page": 0,
        "size": 20,
        "retention_months": 12,
        "now": datetime(2026, 8, 4, tzinfo=UTC),
    }
    params[field] = value

    with pytest.raises(NamespaceAnalyticsError, match="error.namespaceAnalytics.invalidFilter"):
        await namespace_repository.list_namespace_analytics(
            FakeNamespaceAnalyticsEngine(FakeNamespaceAnalyticsConnection()),
            **params,
        )


@pytest.mark.anyio
async def test_namespace_analytics_clamps_repository_pagination() -> None:
    connection = FakeNamespaceAnalyticsConnection()

    result = await namespace_repository.list_namespace_analytics(
        FakeNamespaceAnalyticsEngine(connection),
        query=None,
        namespace_type="ALL",
        namespace_status="ACTIVE",
        start_time=None,
        end_time=None,
        source=None,
        sort="periodDownloads",
        direction="desc",
        page=-2,
        size=500,
        retention_months=-1,
        now=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert result["page"] == 0
    assert result["size"] == 100
    assert result["period"]["retentionMonths"] == 0
    assert connection.params[1]["limit"] == 100
    assert connection.params[1]["offset"] == 0
