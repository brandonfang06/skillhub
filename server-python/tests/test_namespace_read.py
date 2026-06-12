from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace.read import (
    NamespaceReadError,
    get_namespace,
    list_my_namespaces,
    list_namespaces,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnect:
    def __init__(self, connection: "FakeNamespaceConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeNamespaceConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeNamespaceConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeNamespaceConnection:
    def __init__(
        self,
        *,
        roles: list[dict[str, Any]],
        namespaces: list[dict[str, Any]],
        dependency_counts: dict[int, dict[str, int]] | None = None,
    ) -> None:
        self.roles = roles
        self.namespaces = namespaces
        self.dependency_counts = dependency_counts or {}
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "FROM namespace_member" in sql and "JOIN namespace" not in sql:
            return FakeResult(self.roles)
        if "EXISTS (SELECT 1 FROM skill" in sql:
            namespace_id = int((params or {})["namespace_id"])
            counts = self.dependency_counts.get(namespace_id, {})
            return FakeResult(
                [
                    {
                        "has_skill": counts.get("skill_count", 0) > 0,
                        "has_review": counts.get("review_count", 0) > 0,
                        "has_promotion": counts.get("promotion_count", 0) > 0,
                    }
                ]
            )
        if "WHERE n.slug = :slug" in sql:
            slug = str((params or {})["slug"])
            return FakeResult([row for row in self.namespaces if row["slug"] == slug])
        return FakeResult(self.namespaces)


def namespace_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 10,
        "slug": "team-a",
        "display_name": "Team A",
        "status": "ACTIVE",
        "description": "Team namespace",
        "type": "TEAM",
        "avatar_url": "https://example.test/team.png",
        "created_by": "owner",
        "created_at": datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_list_namespaces_scopes_to_active_memberships_sorted_and_paginated() -> None:
    connection = FakeNamespaceConnection(
        roles=[
            {"namespace_id": 10, "role": "OWNER"},
            {"namespace_id": 20, "role": "MEMBER"},
            {"namespace_id": 30, "role": "ADMIN"},
        ],
        namespaces=[
            namespace_row(id=30, slug="zeta"),
            namespace_row(id=20, slug="archived", status="ARCHIVED"),
            namespace_row(id=10, slug="alpha"),
        ],
    )

    response = await list_namespaces(FakeEngine(connection), user_id="user-1", page=0, size=10)

    assert response["total"] == 2
    assert [item["slug"] for item in response["items"]] == ["alpha", "zeta"]
    assert response["items"][0]["createdAt"] == "2026-06-10T08:00:00Z"
    assert connection.params[0] == {"user_id": "user-1"}


@pytest.mark.anyio
async def test_list_my_namespaces_includes_flags_and_dependency_sensitive_delete() -> None:
    connection = FakeNamespaceConnection(
        roles=[
            {"namespace_id": 1, "role": "OWNER"},
            {"namespace_id": 2, "role": "ADMIN"},
            {"namespace_id": 3, "role": "OWNER"},
        ],
        namespaces=[
            namespace_row(id=1, slug="global", type="GLOBAL", status="ACTIVE"),
            namespace_row(id=2, slug="frozen", status="FROZEN"),
            namespace_row(id=3, slug="team-a", status="ACTIVE"),
        ],
        dependency_counts={3: {"skill_count": 1}},
    )

    response = await list_my_namespaces(FakeEngine(connection), user_id="user-1")

    assert [item["slug"] for item in response] == ["frozen", "global", "team-a"]
    frozen = response[0]
    global_ns = response[1]
    team = response[2]
    assert frozen["canUnfreeze"] is True
    assert frozen["canFreeze"] is False
    assert global_ns["immutable"] is True
    assert global_ns["canDelete"] is False
    assert team["currentUserRole"] == "OWNER"
    assert team["canFreeze"] is True
    assert team["canDelete"] is False


@pytest.mark.anyio
async def test_get_namespace_requires_membership_and_hides_archived_from_non_members() -> None:
    non_member = FakeNamespaceConnection(roles=[], namespaces=[namespace_row(slug="team-a")])
    with pytest.raises(NamespaceReadError, match="error.namespace.membership.required") as forbidden:
        await get_namespace(FakeEngine(non_member), slug="team-a", user_id="user-1")
    assert forbidden.value.status_code == 403

    archived = FakeNamespaceConnection(roles=[], namespaces=[namespace_row(slug="old", status="ARCHIVED")])
    with pytest.raises(NamespaceReadError, match="error.namespace.slug.notFound") as not_found:
        await get_namespace(FakeEngine(archived), slug="old", user_id="user-1")
    assert not_found.value.status_code == 400


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_namespace_routes_use_java_envelopes() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def list_reader(user_id: str, page: int, size: int) -> dict[str, object]:
        return {"items": [{"id": 1, "slug": "team-a"}], "total": 1, "page": page, "size": size}

    async def my_reader(user_id: str) -> list[dict[str, object]]:
        return [{"id": 1, "slug": "team-a", "currentUserRole": "OWNER"}]

    async def detail_reader(slug: str, user_id: str) -> dict[str, object]:
        return {"id": 1, "slug": slug}

    app.state.namespace_list_reader = list_reader
    app.state.my_namespace_reader = my_reader
    app.state.namespace_detail_reader = detail_reader
    client = TestClient(app)

    assert client.get("/api/v1/namespaces").status_code == 401

    list_response = client.get(
        "/api/web/namespaces?page=2&size=5",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "ns-list"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["requestId"] == "ns-list"
    assert list_response.json()["data"]["page"] == 2
    assert list_response.json()["data"]["size"] == 5

    mine_response = client.get("/api/v1/me/namespaces", headers={"X-Mock-User-Id": "user-1"})
    assert mine_response.status_code == 200
    assert mine_response.json()["data"][0]["currentUserRole"] == "OWNER"

    detail_response = client.get("/api/web/namespaces/team-a", headers={"X-Mock-User-Id": "user-1"})
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["slug"] == "team-a"


def test_namespace_list_accepts_session_principal() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: auth_user("user-1")

    async def list_reader(user_id: str, page: int, size: int) -> dict[str, object]:
        return {"items": [{"id": 1, "slug": "team-a"}], "total": 1, "page": page, "size": size}

    app.state.namespace_list_reader = list_reader
    client = TestClient(app)

    login = client.post("/api/v1/auth/local/login", json={"username": "user-1", "password": "Abcd123!"})
    list_response = client.get("/api/v1/namespaces?page=0&size=20")

    assert login.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"] == [{"id": 1, "slug": "team-a"}]
