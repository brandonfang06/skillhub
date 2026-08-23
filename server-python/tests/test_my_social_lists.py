from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.lists import list_my_social_skills


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, *, scalar: int | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one(self) -> int:
        if self.scalar is None:
            raise AssertionError("scalar result was not configured")
        return self.scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnect:
    def __init__(self, connection: "FakeListConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeListConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeListConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeListConnection:
    def __init__(self, *, total: int, rows: list[dict[str, Any]]) -> None:
        self.total = total
        self.rows = rows
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)
        if "COUNT(*)" in sql:
            return FakeResult(scalar=self.total)
        return FakeResult(rows=self.rows)


def social_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 42,
        "slug": "demo-skill",
        "display_name": "Demo Skill",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 8,
        "star_count": 2,
        "rating_avg": Decimal("4.25"),
        "rating_count": 3,
        "namespace": "global",
        "updated_at": datetime(2026, 6, 10, 11, 0, tzinfo=UTC),
        "published_version_id": 77,
        "published_version": "1.0.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_list_my_social_skills_maps_stars_with_java_page_defaults_and_total() -> None:
    connection = FakeListConnection(total=2, rows=[social_row()])

    response = await list_my_social_skills(FakeEngine(connection), kind="stars", user_id="user-1", page=0, size=12)

    assert response == {
        "items": [
            {
                "id": 42,
                "slug": "demo-skill",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "visibility": "PUBLIC",
                "status": "ACTIVE",
                "downloadCount": 8,
                "starCount": 2,
                "ratingAvg": 4.25,
                "ratingCount": 3,
                "namespace": "global",
                "updatedAt": "2026-06-10T11:00:00Z",
                "canSubmitPromotion": False,
                "headlineVersion": {"id": 77, "version": "1.0.0", "status": "PUBLISHED"},
                "publishedVersion": {"id": 77, "version": "1.0.0", "status": "PUBLISHED"},
                "ownerPreviewVersion": None,
                "resolutionMode": "PUBLISHED",
                "complianceSnapshot": None,
            }
        ],
        "total": 2,
        "page": 0,
        "size": 12,
    }
    assert connection.params[0] == {"user_id": "user-1"}
    assert connection.params[1]["limit"] == 12
    assert connection.params[1]["offset"] == 0
    assert "skill_star" in connection.statements[0]
    assert "skill_star" in connection.statements[1]


@pytest.mark.anyio
async def test_list_my_social_skills_filters_missing_skills_but_preserves_social_total() -> None:
    connection = FakeListConnection(total=1, rows=[])

    response = await list_my_social_skills(FakeEngine(connection), kind="subscriptions", user_id="user-1", page=1, size=5)

    assert response == {"items": [], "total": 1, "page": 1, "size": 5}
    assert connection.params[1]["limit"] == 5
    assert connection.params[1]["offset"] == 5
    assert "skill_subscription" in connection.statements[0]
    assert "skill_subscription" in connection.statements[1]


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_my_social_list_routes_use_java_envelopes_and_require_authentication() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def reader(kind: str, user_id: str, page: int, size: int) -> dict[str, object]:
        return {
            "items": [{"id": 1, "slug": kind, "displayName": user_id}],
            "total": 1,
            "page": page,
            "size": size,
        }

    app.state.my_social_list_reader = reader
    client = TestClient(app)

    assert client.get("/api/v1/me/stars").status_code == 401

    stars_response = client.get(
        "/api/v1/me/stars?page=2&size=4",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "stars-page"},
    )
    subscriptions_response = client.get(
        "/api/web/me/subscriptions",
        headers={"X-Mock-User-Id": "user-1"},
    )

    assert stars_response.status_code == 200
    assert stars_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert stars_response.json()["requestId"] == "stars-page"
    assert stars_response.json()["data"]["items"][0]["slug"] == "stars"
    assert stars_response.json()["data"]["page"] == 2
    assert stars_response.json()["data"]["size"] == 4
    assert subscriptions_response.status_code == 200
    assert subscriptions_response.json()["data"]["items"][0]["slug"] == "subscriptions"
    assert subscriptions_response.json()["data"]["page"] == 0
    assert subscriptions_response.json()["data"]["size"] == 12
