from __future__ import annotations

import asyncio
import csv
from datetime import UTC, datetime
import io
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest

import app.download_analytics.repository as download_repository
import app.main as main_module
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return int(self.scalar if self.scalar is not None else len(self.rows))

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeTransaction:
    def __init__(self, connection: "FakeDownloadAnalyticsConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeDownloadAnalyticsConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeDownloadAnalyticsEngine:
    def __init__(self, connection: "FakeDownloadAnalyticsConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeDownloadAnalyticsConnection:
    def __init__(
        self,
        *,
        skill: dict[str, Any] | None = None,
        namespace_role: str | None = None,
    ) -> None:
        self.skill = skill or {"id": 7, "owner_id": "owner-user", "namespace_id": 10}
        self.namespace_role = namespace_role
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.rows = [
            {
                "id": 2,
                "skill_id": 7,
                "skill_version_id": 43,
                "namespace_slug": "team-a",
                "skill_slug": "demo",
                "version": "1.1.0",
                "source": "cli",
                "user_id": None,
                "display_name": None,
                "request_id": "request-2",
                "client_ip": "127.0.0.2",
                "user_agent": "skillhub-cli",
                "created_at": datetime(2026, 7, 8, 10, 2, tzinfo=UTC),
            },
            {
                "id": 1,
                "skill_id": 7,
                "skill_version_id": 42,
                "namespace_slug": "team-a",
                "skill_slug": "demo",
                "version": "1.0.0",
                "source": "web",
                "user_id": "user-a",
                "display_name": "User A",
                "request_id": "request-1",
                "client_ip": "127.0.0.1",
                "user_agent": "pytest",
                "created_at": datetime(2026, 7, 8, 10, 1, tzinfo=UTC),
            },
        ]

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "FROM skill s" in sql and "JOIN namespace n" in sql:
            return FakeResult(rows=[self.skill] if self.skill is not None else [])
        if "FROM namespace_member" in sql:
            return FakeResult(scalar=self.namespace_role)
        filtered = self._filtered(bound)
        if "COUNT(*)" in sql:
            return FakeResult(scalar=len(filtered))
        if "FROM local_skill_download_event" in sql:
            offset = int(bound.get("offset", 0))
            limit = int(bound.get("limit", len(filtered)))
            return FakeResult(rows=filtered[offset : offset + limit])
        raise AssertionError(f"unexpected SQL: {sql}")

    def _filtered(self, bound: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.rows)
        if bound.get("namespace"):
            rows = [row for row in rows if row["namespace_slug"] == bound["namespace"]]
        if bound.get("slug"):
            rows = [row for row in rows if row["skill_slug"] == bound["slug"]]
        if bound.get("version"):
            rows = [row for row in rows if row["version"] == bound["version"]]
        if bound.get("user_id"):
            rows = [row for row in rows if row["user_id"] == bound["user_id"]]
        if bound.get("user_query"):
            query = str(bound["user_query"]).strip("%").lower()
            rows = [
                row
                for row in rows
                if query in str(row.get("display_name") or "").lower()
                or query in str(row.get("user_id") or "").lower()
            ]
        if bound.get("source"):
            rows = [row for row in rows if row["source"] == bound["source"]]
        return sorted([row.copy() for row in rows], key=lambda row: row["created_at"], reverse=True)


class FakeDownloadAnalyticsWriteConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        return FakeResult()


class FakeRedisClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_record_skill_download_event_truncates_untrusted_metadata() -> None:
    connection = FakeDownloadAnalyticsWriteConnection()

    await download_repository.record_skill_download_event(
        connection,
        skill_id=7,
        skill_version_id=42,
        namespace="team-a",
        slug="demo",
        version="1.0.0",
        context=download_repository.DownloadEventContext(
            user_id="user-a",
            source="web",
            request_id="r" * 80,
            client_ip="1" * 80,
            user_agent="agent/" + ("x" * 700),
        ),
    )

    params = connection.params[0]
    assert len(params["request_id"]) == 64
    assert len(params["client_ip"]) == 64
    assert len(params["user_agent"]) == 512


@pytest.mark.anyio
async def test_prune_expired_download_events_uses_month_retention() -> None:
    connection = FakeDownloadAnalyticsWriteConnection()

    deleted = await download_repository.prune_expired_download_events(connection, retention_months=12)

    assert deleted == 0
    assert "DELETE FROM local_skill_download_event" in connection.statements[0]
    assert "INTERVAL '1 month'" in connection.statements[0]
    assert connection.params[0] == {"retention_months": 12}


@pytest.mark.anyio
async def test_prune_expired_download_events_skips_when_disabled() -> None:
    connection = FakeDownloadAnalyticsWriteConnection()

    deleted = await download_repository.prune_expired_download_events(connection, retention_months=0)

    assert deleted == 0
    assert connection.statements == []


@pytest.mark.anyio
async def test_lifespan_starts_and_stops_download_analytics_retention_task(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(download_analytics_retention_months=12)
    engine = object()
    redis_client = FakeRedisClient()
    retention_started = asyncio.Event()
    retention_cancelled = asyncio.Event()
    disposed: list[object] = []
    outbox_events: list[str] = []

    class FakeOutboxDaemon:
        def start(self) -> None:
            outbox_events.append("start")

        async def shutdown(self) -> None:
            outbox_events.append("shutdown")

    async def fake_initialize_bootstrap_admin(current_engine: object) -> None:
        assert current_engine is engine

    async def fake_run_builtin_skill_sync(current_engine: object, current_settings: object) -> None:
        assert current_engine is engine
        assert current_settings is settings
        await asyncio.Event().wait()

    async def fake_run_download_analytics_retention_loop(current_engine: object, retention_months: int) -> None:
        assert current_engine is engine
        assert retention_months == 12
        retention_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            retention_cancelled.set()
            raise

    async def fake_dispose_database_engine(current_engine: object) -> None:
        disposed.append(current_engine)

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "create_database_engine", lambda current_settings: engine)
    monkeypatch.setattr(main_module, "create_redis_client", lambda current_settings: redis_client)
    monkeypatch.setattr(main_module, "initialize_bootstrap_admin", fake_initialize_bootstrap_admin)
    monkeypatch.setattr(main_module, "run_builtin_skill_sync", fake_run_builtin_skill_sync)
    monkeypatch.setattr(
        main_module,
        "run_download_analytics_retention_loop",
        fake_run_download_analytics_retention_loop,
    )
    monkeypatch.setattr(main_module, "create_scan_consumer_daemon", lambda *_args: None)
    monkeypatch.setattr(
        main_module,
        "create_scan_outbox_daemon",
        lambda *_args: FakeOutboxDaemon(),
    )
    monkeypatch.setattr(main_module, "dispose_database_engine", fake_dispose_database_engine)

    app = create_app()

    async with main_module.lifespan(app):
        await asyncio.wait_for(retention_started.wait(), timeout=1)
        assert app.state.download_analytics_retention_task is not None
        assert outbox_events == ["start"]

    await asyncio.wait_for(retention_cancelled.wait(), timeout=1)
    assert redis_client.closed is True
    assert disposed == [engine]
    assert outbox_events == ["start", "shutdown"]


@pytest.mark.anyio
async def test_admin_download_events_filter_and_project_fields() -> None:
    connection = FakeDownloadAnalyticsConnection()

    response = await download_repository.list_admin_download_events(
        FakeDownloadAnalyticsEngine(connection),
        page=0,
        size=20,
        namespace=" team-a ",
        slug=" demo ",
        version="1.0.0",
        user_id=" user-a ",
        source=" WEB ",
        start_time="2026-07-08T10:00:00Z",
        end_time="2026-07-08T11:00:00Z",
        platform_roles=["AUDITOR"],
    )

    assert response == {
        "items": [
            {
                "id": 1,
                "skillId": 7,
                "skillVersionId": 42,
                "namespace": "team-a",
                "slug": "demo",
                "version": "1.0.0",
                "source": "web",
                "userId": "user-a",
                "username": "User A",
                "requestId": "request-1",
                "ipAddress": "127.0.0.1",
                "userAgent": "pytest",
                "createdAt": "2026-07-08T10:01:00Z",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }
    assert connection.params[0]["source"] == "web"
    assert connection.params[0]["start_time"].tzinfo is not None


@pytest.mark.anyio
async def test_admin_download_events_filter_by_user_name_or_id() -> None:
    connection = FakeDownloadAnalyticsConnection()
    template = connection.rows[1]
    connection.rows = [
        template,
        dict(
            template,
            id=3,
            user_id="user-b",
            display_name="USER A",
            created_at=datetime(2026, 7, 8, 10, 3, tzinfo=UTC),
        ),
        dict(
            template,
            id=4,
            user_id="user-c",
            display_name="Different User",
            created_at=datetime(2026, 7, 8, 10, 4, tzinfo=UTC),
        ),
    ]

    by_name = await download_repository.list_admin_download_events(
        FakeDownloadAnalyticsEngine(connection),
        page=0,
        size=20,
        namespace=None,
        slug=None,
        version=None,
        user_id=None,
        user_query=" User A ",
        source=None,
        start_time=None,
        end_time=None,
        platform_roles=["AUDITOR"],
    )
    by_id = await download_repository.list_admin_download_events(
        FakeDownloadAnalyticsEngine(connection),
        page=0,
        size=20,
        namespace=None,
        slug=None,
        version=None,
        user_id=None,
        user_query=" SER-B ",
        source=None,
        start_time=None,
        end_time=None,
        platform_roles=["AUDITOR"],
    )

    assert {item["userId"] for item in by_name["items"]} == {"user-a", "user-b"}
    assert [item["userId"] for item in by_id["items"]] == ["user-b"]
    assert connection.params[0]["user_query"] == "%user a%"
    assert "LEFT JOIN user_account ua ON ua.id = de.user_id" in connection.statements[0]

    wildcard_where, wildcard_params = download_repository._where_clause(
        namespace=None,
        slug=None,
        version=None,
        user_id=None,
        user_query=" User_% ",
        source=None,
        start_time=None,
        end_time=None,
    )
    assert "LIKE :user_query ESCAPE '!'" in wildcard_where
    assert wildcard_params["user_query"] == "%user!_!%%"


@pytest.mark.anyio
async def test_admin_download_events_require_platform_reader_role() -> None:
    with pytest.raises(download_repository.DownloadAnalyticsError, match="error.downloadAnalytics.readDenied") as denied:
        await download_repository.list_admin_download_events(
            FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection()),
            page=0,
            size=20,
            namespace=None,
            slug=None,
            version=None,
            user_id=None,
            source=None,
            start_time=None,
            end_time=None,
            platform_roles=["USER"],
        )

    assert denied.value.status_code == 403


@pytest.mark.anyio
async def test_skill_download_events_allow_owner_and_namespace_manager() -> None:
    owner_response = await download_repository.list_skill_download_events(
        FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection()),
        namespace="team-a",
        slug="demo",
        page=0,
        size=20,
        version=None,
        user_id=None,
        source=None,
        start_time=None,
        end_time=None,
        actor_user_id="owner-user",
        platform_roles=["USER"],
    )
    manager_response = await download_repository.list_skill_download_events(
        FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection(namespace_role="ADMIN")),
        namespace="team-a",
        slug="demo",
        page=0,
        size=20,
        version=None,
        user_id=None,
        source=None,
        start_time=None,
        end_time=None,
        actor_user_id="namespace-admin",
        platform_roles=["USER"],
    )

    assert owner_response["total"] == 2
    assert manager_response["total"] == 2


@pytest.mark.anyio
async def test_skill_download_events_reject_unrelated_user() -> None:
    with pytest.raises(download_repository.DownloadAnalyticsError, match="error.downloadAnalytics.readDenied") as denied:
        await download_repository.list_skill_download_events(
            FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection(namespace_role="MEMBER")),
            namespace="team-a",
            slug="demo",
            page=0,
            size=20,
            version=None,
            user_id=None,
            source=None,
            start_time=None,
            end_time=None,
            actor_user_id="member-user",
            platform_roles=["USER"],
        )

    assert denied.value.status_code == 403


def test_admin_download_events_route_uses_envelope_and_roles() -> None:
    app = create_app()
    app.state.db_engine = FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection())
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SKILL_ADMIN"],
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/download-events",
        headers={"X-Mock-User-Id": "admin-user"},
        params={
            "namespace": "team-a",
            "slug": "demo",
            "userQuery": "User A",
            "size": "1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["userId"] == "user-a"


def test_admin_download_events_csv_route_exports_filtered_rows() -> None:
    app = create_app()
    connection = FakeDownloadAnalyticsConnection()
    app.state.db_engine = FakeDownloadAnalyticsEngine(connection)
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["AUDITOR"],
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/download-events.csv",
        headers={"X-Mock-User-Id": "admin-user"},
        params={"namespace": "team-a", "userQuery": "User A", "source": "web"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="skillhub-download-events.csv"'
    assert response.headers["x-skillhub-export-truncated"] == "false"
    assert response.headers["x-skillhub-export-row-limit"] == "10000"
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows == [
        {
            "createdAt": "2026-07-08T10:01:00Z",
            "namespace": "team-a",
            "slug": "demo",
            "version": "1.0.0",
            "source": "web",
            "userId": "user-a",
            "username": "User A",
            "ipAddress": "127.0.0.1",
            "userAgent": "pytest",
            "requestId": "request-1",
            "skillId": "7",
            "skillVersionId": "42",
        }
    ]
    assert any(params.get("limit") == 10_001 for params in connection.params)


def test_admin_download_events_csv_route_marks_truncated_exports() -> None:
    app = create_app()
    connection = FakeDownloadAnalyticsConnection()
    template = connection.rows[0]
    connection.rows = [dict(template, id=index) for index in range(10_001)]
    app.state.db_engine = FakeDownloadAnalyticsEngine(connection)
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["AUDITOR"],
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/admin/download-events.csv",
        headers={"X-Mock-User-Id": "admin-user"},
    )

    assert response.status_code == 200
    assert response.headers["x-skillhub-export-truncated"] == "true"
    assert response.headers["x-skillhub-export-row-limit"] == "10000"
    assert len(list(csv.DictReader(io.StringIO(response.text)))) == 10_000


def test_admin_download_events_route_rejects_normal_user() -> None:
    app = create_app()
    app.state.db_engine = FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection())
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }

    client = TestClient(app)
    response = client.get("/api/v1/admin/download-events", headers={"X-Mock-User-Id": "normal-user"})

    assert response.status_code == 403


def test_admin_download_events_csv_route_rejects_normal_user() -> None:
    app = create_app()
    app.state.db_engine = FakeDownloadAnalyticsEngine(FakeDownloadAnalyticsConnection())
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }

    client = TestClient(app)
    response = client.get("/api/v1/admin/download-events.csv", headers={"X-Mock-User-Id": "normal-user"})

    assert response.status_code == 403


def test_render_download_events_csv_neutralizes_formula_cells() -> None:
    csv_body = download_repository.render_download_events_csv(
        [
            {
                "createdAt": "2026-07-08T10:01:00Z",
                "namespace": "team-a",
                "slug": "demo",
                "version": "1.0.0",
                "source": "web",
                "userId": "user-a",
                "username": "=cmd|' /C calc'!A0",
                "ipAddress": "127.0.0.1",
                "userAgent": "+SUM(1,1)",
                "requestId": "request-1",
                "skillId": 7,
                "skillVersionId": 42,
            }
        ]
    )

    row = next(csv.DictReader(io.StringIO(csv_body)))
    assert row["username"].startswith("'=")
    assert row["userAgent"].startswith("'+")
