from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace_analytics import repository as namespace_repository
from app.namespace_analytics.repository import NamespaceAnalyticsError, resolve_period
from scripts.export_namespace_analytics_openapi import build_openapi_schema


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
    def __init__(self, export_rows: list[dict[str, Any]] | None = None) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.export_rows = export_rows

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
        if "namespace-analytics-export" in sql:
            return FakeResult(
                self.export_rows
                if self.export_rows is not None
                else [
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


def test_render_namespace_analytics_csv_is_excel_safe_and_analysis_ready() -> None:
    period = namespace_repository.ResolvedPeriod(
        start_time=datetime(2026, 7, 5, tzinfo=UTC),
        end_time=datetime(2026, 8, 4, 12, 30, tzinfo=UTC),
    )
    items = [
        {
            "namespaceId": 7,
            "slug": "platform,tools",
            "displayName": "=危險名稱",
            "type": "TEAM",
            "status": "ACTIVE",
            "maintainerCount": 2,
            "skillCount": 4,
            "lifetimeDownloads": 30,
            "periodDownloads": 8,
        }
    ]

    csv_body = namespace_repository.render_namespace_analytics_csv(items, period, source="cli")

    assert csv_body.startswith("\ufeffnamespace_id,namespace_slug,display_name,namespace_type")
    rows = list(csv.DictReader(io.StringIO(csv_body.removeprefix("\ufeff"))))
    assert rows == [
        {
            "namespace_id": "7",
            "namespace_slug": "platform,tools",
            "display_name": "'=危險名稱",
            "namespace_type": "TEAM",
            "namespace_status": "ACTIVE",
            "maintainer_count": "2",
            "skill_count": "4",
            "lifetime_downloads": "30",
            "period_downloads": "8",
            "period_start_time": "2026-07-05T00:00:00+00:00",
            "period_end_time": "2026-08-04T12:30:00+00:00",
            "source": "cli",
        }
    ]


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r", "\n"])
def test_render_namespace_analytics_csv_neutralizes_formula_prefixes(prefix: str) -> None:
    period = namespace_repository.ResolvedPeriod(
        start_time=datetime(2026, 7, 5, tzinfo=UTC),
        end_time=datetime(2026, 8, 4, tzinfo=UTC),
    )

    csv_body = namespace_repository.render_namespace_analytics_csv(
        [
            {
                "namespaceId": 1,
                "slug": f"{prefix}slug",
                "displayName": f"{prefix}name",
                "type": "TEAM",
                "status": "ACTIVE",
                "maintainerCount": 0,
                "skillCount": 0,
                "lifetimeDownloads": 0,
                "periodDownloads": 0,
            }
        ],
        period,
        source=None,
    )

    row = next(csv.DictReader(io.StringIO(csv_body.removeprefix("\ufeff"))))
    assert row["namespace_slug"] == f"'{prefix}slug"
    assert row["display_name"] == f"'{prefix}name"
    assert row["source"] == ""


def test_render_namespace_analytics_csv_returns_header_for_empty_export() -> None:
    period = namespace_repository.ResolvedPeriod(
        start_time=datetime(2026, 7, 5, tzinfo=UTC),
        end_time=datetime(2026, 8, 4, tzinfo=UTC),
    )

    csv_body = namespace_repository.render_namespace_analytics_csv([], period, source=None)

    assert len(csv_body.removeprefix("\ufeff").splitlines()) == 1


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


@pytest.mark.anyio
async def test_export_namespace_analytics_csv_uses_all_filters_without_pagination() -> None:
    connection = FakeNamespaceAnalyticsConnection()

    csv_body, truncated = await namespace_repository.export_namespace_analytics_csv(
        FakeNamespaceAnalyticsEngine(connection),
        query=" platform ",
        namespace_type="team",
        namespace_status="all",
        start_time="2026-07-05T00:00:00Z",
        end_time="2026-08-04T00:00:00Z",
        source="WEB",
        sort="skills",
        direction="ASC",
    )

    assert truncated is False
    assert len(list(csv.DictReader(io.StringIO(csv_body.removeprefix("\ufeff"))))) == 2
    assert len(connection.statements) == 1
    assert "namespace-analytics-export" in connection.statements[0]
    assert "skill_count ASC, slug ASC" in connection.statements[0]
    assert connection.params[0] == {
        "query": "%platform%",
        "namespace_type": "TEAM",
        "namespace_status": None,
        "start_time": datetime(2026, 7, 5, tzinfo=UTC),
        "end_time": datetime(2026, 8, 4, tzinfo=UTC),
        "source": "web",
        "limit": 10_001,
    }


@pytest.mark.anyio
async def test_export_namespace_analytics_csv_caps_rows_and_reports_truncation() -> None:
    export_rows = [
        {
            "namespace_id": index,
            "slug": f"namespace-{index}",
            "display_name": f"Namespace {index}",
            "type": "TEAM",
            "status": "ACTIVE",
            "maintainer_count": 1,
            "skill_count": 1,
            "lifetime_downloads": index,
            "period_downloads": index,
        }
        for index in range(10_001)
    ]
    connection = FakeNamespaceAnalyticsConnection(export_rows)

    csv_body, truncated = await namespace_repository.export_namespace_analytics_csv(
        FakeNamespaceAnalyticsEngine(connection),
        query=None,
        namespace_type="ALL",
        namespace_status="ACTIVE",
        start_time=None,
        end_time=None,
        source=None,
        sort="periodDownloads",
        direction="desc",
        now=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert truncated is True
    assert len(list(csv.DictReader(io.StringIO(csv_body.removeprefix("\ufeff"))))) == 10_000
    assert connection.params[0]["limit"] == 10_001


def auth_user(user_id: str, roles: list[str], *, provider: str = "mock") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": provider,
        "platformRoles": roles,
    }


def namespace_analytics_app(roles: list[str]) -> object:
    app = create_app()
    app.state.db_engine = FakeNamespaceAnalyticsEngine(FakeNamespaceAnalyticsConnection())
    app.state.settings = SimpleNamespace(download_analytics_retention_months=12)
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, roles)
    return app


def test_namespace_analytics_route_uses_envelope_request_id_and_defaults() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics",
        headers={"X-Mock-User-Id": "platform-admin", "X-Request-Id": "analytics-test"},
        params={"endTime": "2026-08-04T00:00:00Z"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["requestId"] == "analytics-test"
    assert body["data"]["summary"]["namespaceCount"] == 2
    assert body["data"]["period"]["startTime"] == "2026-07-05T00:00:00Z"
    assert body["data"]["period"]["retentionMonths"] == 12


def test_namespace_analytics_route_requires_authentication() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get("/api/v1/admin/namespace-analytics")

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


@pytest.mark.parametrize("roles", [["USER"], ["SKILL_ADMIN"], ["AUDITOR"]])
def test_namespace_analytics_route_requires_super_admin(roles: list[str]) -> None:
    app = namespace_analytics_app(roles)
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics",
        headers={"X-Mock-User-Id": "not-super-admin"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.admin.superAdminRequired"


def test_namespace_analytics_route_rejects_bearer_api_token() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    app.state.auth_bearer_reader = lambda token: auth_user("token-admin", ["SUPER_ADMIN"], provider="api_token")
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics",
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 403
    assert response.json()["msg"] == "error.apiToken.endpoint.unsupported"
    assert response.json()["data"]["args"] == ["/api/v1/admin/namespace-analytics"]


@pytest.mark.parametrize(
    "params",
    [
        {"namespaceType": "PERSONAL"},
        {"namespaceStatus": "DELETED"},
        {"source": "mobile"},
        {"sort": "owner"},
        {"direction": "sideways"},
        {"page": "-1"},
        {"size": "101"},
    ],
)
def test_namespace_analytics_route_validates_query_boundary(params: dict[str, str]) -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics",
        headers={"X-Mock-User-Id": "platform-admin"},
        params=params,
    )

    assert response.status_code == 422


def test_namespace_analytics_route_rejects_reversed_period() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics",
        headers={"X-Mock-User-Id": "platform-admin"},
        params={"startTime": "2026-08-04T00:00:00Z", "endTime": "2026-08-03T00:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.namespaceAnalytics.invalidTimeRange"


def test_namespace_analytics_csv_route_exports_filtered_rows_with_metadata() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics.csv",
        headers={"X-Mock-User-Id": "platform-admin"},
        params={
            "query": "platform",
            "namespaceType": "TEAM",
            "namespaceStatus": "ALL",
            "startTime": "2026-07-05T00:00:00Z",
            "endTime": "2026-08-04T00:00:00Z",
            "source": "web",
            "sort": "skills",
            "direction": "asc",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert response.headers["content-disposition"] == (
        'attachment; filename="skillhub-namespace-analytics.csv"'
    )
    assert response.headers["x-skillhub-export-truncated"] == "false"
    assert response.headers["x-skillhub-export-row-limit"] == "10000"
    assert response.content.startswith(b"\xef\xbb\xbfnamespace_id,namespace_slug")
    rows = list(csv.DictReader(io.StringIO(response.text.removeprefix("\ufeff"))))
    assert [row["namespace_slug"] for row in rows] == ["global", "platform-tools"]
    assert {row["source"] for row in rows} == {"web"}


def test_namespace_analytics_csv_route_requires_authentication() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get("/api/v1/admin/namespace-analytics.csv")

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


@pytest.mark.parametrize("roles", [["USER"], ["SKILL_ADMIN"], ["AUDITOR"]])
def test_namespace_analytics_csv_route_requires_super_admin(roles: list[str]) -> None:
    app = namespace_analytics_app(roles)
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics.csv",
        headers={"X-Mock-User-Id": "not-super-admin"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.admin.superAdminRequired"


def test_namespace_analytics_csv_route_rejects_bearer_api_token() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    app.state.auth_bearer_reader = lambda token: auth_user("token-admin", ["SUPER_ADMIN"], provider="api_token")
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics.csv",
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 403
    assert response.json()["msg"] == "error.apiToken.endpoint.unsupported"
    assert response.json()["data"]["args"] == ["/api/v1/admin/namespace-analytics.csv"]


def test_namespace_analytics_csv_route_rejects_reversed_period() -> None:
    app = namespace_analytics_app(["SUPER_ADMIN"])
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics.csv",
        headers={"X-Mock-User-Id": "platform-admin"},
        params={"startTime": "2026-08-04T00:00:00Z", "endTime": "2026-08-03T00:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.namespaceAnalytics.invalidTimeRange"


def test_namespace_analytics_openapi_exposes_typed_contract() -> None:
    schema = create_app().openapi()

    operation = schema["paths"]["/api/v1/admin/namespace-analytics"]["get"]
    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success_schema["$ref"].endswith("/NamespaceAnalyticsEnvelope")
    assert "NamespaceAnalyticsData" in schema["components"]["schemas"]
    item_schema = schema["components"]["schemas"]["NamespaceAnalyticsItem"]
    assert item_schema["properties"]["type"]["enum"] == ["GLOBAL", "TEAM"]
    assert item_schema["properties"]["status"]["enum"] == ["ACTIVE", "FROZEN", "ARCHIVED"]


def test_focused_namespace_analytics_openapi_contains_only_analytics_route() -> None:
    schema = build_openapi_schema()

    assert list(schema["paths"]) == [
        "/api/v1/admin/namespace-analytics",
        "/api/v1/admin/namespace-analytics.csv",
        "/api/v1/admin/namespace-analytics/security",
        "/api/v1/admin/namespace-analytics/security/namespaces/{namespace_id}/skills",
    ]
    assert schema["info"]["title"] == "SkillHub Namespace Analytics API"
