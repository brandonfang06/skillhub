from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.owned import list_my_owned_skills


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnect:
    def __init__(self, connection: "FakeOwnedConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeOwnedConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeOwnedConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeOwnedConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        return FakeResult(self.rows)


def owned_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 101,
        "slug": "demo",
        "display_name": "Demo Skill",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "hidden": False,
        "download_count": 3,
        "star_count": 2,
        "rating_avg": Decimal("4.50"),
        "rating_count": 4,
        "namespace": "team-a",
        "namespace_type": "TEAM",
        "namespace_status": "ACTIVE",
        "updated_at": datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        "published_version_id": 501,
        "published_version": "1.0.0",
        "published_version_status": "PUBLISHED",
        "owner_preview_version_id": 601,
        "owner_preview_version": "1.1.0",
        "owner_preview_version_status": "PENDING_REVIEW",
        "promotion_blocked": False,
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_list_my_owned_skills_default_includes_archived_hidden_and_owner_preview() -> None:
    rows = [
        owned_row(),
        owned_row(id=102, slug="archived", status="ARCHIVED", published_version_id=None, owner_preview_version_id=None),
        owned_row(id=103, slug="hidden", hidden=True, published_version_id=None, owner_preview_version_id=None),
    ]
    connection = FakeOwnedConnection(rows)

    response = await list_my_owned_skills(
        FakeEngine(connection),
        user_id="user-1",
        platform_roles=set(),
        page=0,
        size=10,
        filter_value=None,
        keyword=None,
        namespace=None,
    )

    assert response["total"] == 3
    assert response["size"] == 10
    assert [item["slug"] for item in response["items"]] == ["demo", "archived", "hidden"]
    assert response["items"][0]["headlineVersion"] == {"id": 501, "version": "1.0.0", "status": "PUBLISHED"}
    assert response["items"][0]["ownerPreviewVersion"] == {"id": 601, "version": "1.1.0", "status": "PENDING_REVIEW"}
    assert response["items"][0]["resolutionMode"] == "PUBLISHED"
    assert response["items"][0]["canSubmitPromotion"] is True
    assert connection.params[0] == {"user_id": "user-1"}
    assert "promotion_request" in connection.statements[0]


@pytest.mark.anyio
async def test_list_my_owned_skills_filter_path_matches_keyword_namespace_and_hides_archived_hidden() -> None:
    rows = [
        owned_row(slug="visible", display_name="Visible Agent", namespace="team-a"),
        owned_row(slug="archived", status="ARCHIVED", namespace="team-a"),
        owned_row(slug="hidden", hidden=True, namespace="team-a"),
        owned_row(slug="other-namespace", namespace="team-b"),
    ]

    response = await list_my_owned_skills(
        FakeEngine(FakeOwnedConnection(rows)),
        user_id="user-1",
        platform_roles=set(),
        page=0,
        size=10,
        filter_value="ALL",
        keyword="agent",
        namespace="team-a",
    )

    assert response["total"] == 1
    assert response["items"][0]["slug"] == "visible"


@pytest.mark.anyio
async def test_list_my_owned_skills_hidden_filter_requires_super_admin() -> None:
    rows = [owned_row(slug="hidden", hidden=True), owned_row(slug="visible")]

    non_admin = await list_my_owned_skills(
        FakeEngine(FakeOwnedConnection(rows)),
        user_id="user-1",
        platform_roles=set(),
        page=0,
        size=10,
        filter_value="HIDDEN",
        keyword=None,
        namespace=None,
    )
    admin = await list_my_owned_skills(
        FakeEngine(FakeOwnedConnection(rows)),
        user_id="user-1",
        platform_roles={"SUPER_ADMIN"},
        page=0,
        size=10,
        filter_value="HIDDEN",
        keyword=None,
        namespace=None,
    )

    assert non_admin == {"items": [], "total": 0, "page": 0, "size": 10}
    assert admin["total"] == 1
    assert admin["items"][0]["slug"] == "hidden"


def auth_user(user_id: str = "user-1", roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["USER"],
    }


def test_my_skills_routes_use_java_envelopes_and_require_authentication() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SUPER_ADMIN"])

    async def reader(
        user_id: str,
        platform_roles: set[str],
        page: int,
        size: int,
        filter_value: str | None,
        keyword: str | None,
        namespace: str | None,
    ) -> dict[str, object]:
        return {
            "items": [{"id": 1, "slug": namespace or "my-skill", "displayName": filter_value or "", "summary": keyword}],
            "total": 1,
            "page": page,
            "size": size,
        }

    app.state.my_skills_reader = reader
    client = TestClient(app)

    assert client.get("/api/v1/me/skills").status_code == 401

    response = client.get(
        "/api/web/me/skills?page=2&size=4&filter=HIDDEN&q=agent&namespace=team-a",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "my-skills"},
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "my-skills"
    assert response.json()["data"]["page"] == 2
    assert response.json()["data"]["size"] == 4
    assert response.json()["data"]["items"][0]["slug"] == "team-a"
    assert response.json()["data"]["items"][0]["displayName"] == "HIDDEN"
    assert response.json()["data"]["items"][0]["summary"] == "agent"
