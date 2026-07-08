from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
import pytest

import app.download_analytics.repository as download_repository
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
        if bound.get("source"):
            rows = [row for row in rows if row["source"] == bound["source"]]
        return sorted([row.copy() for row in rows], key=lambda row: row["created_at"], reverse=True)


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
        params={"namespace": "team-a", "slug": "demo", "size": "1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 2
    assert body["data"]["items"][0]["source"] == "cli"


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
