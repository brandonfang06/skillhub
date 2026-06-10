from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace.members import (
    NamespaceMemberReadError,
    list_namespace_members,
    search_namespace_member_candidates,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self.rows = rows if rows is not None else ([row] if row is not None else [])

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return int(self.rows[0]["count"])


class FakeConnect:
    def __init__(self, connection: "FakeNamespaceMemberConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeNamespaceMemberConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeNamespaceMemberConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeNamespaceMemberConnection:
    def __init__(
        self,
        *,
        namespace: dict[str, Any] | None = None,
        role: str | None = "OWNER",
        members: list[dict[str, Any]] | None = None,
        users: list[dict[str, Any]] | None = None,
        existing_member_ids: list[str] | None = None,
    ) -> None:
        self.namespace = namespace or namespace_row()
        self.role = role
        self.members = members or []
        self.users = users or []
        self.existing_member_ids = existing_member_ids or []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "FROM namespace n" in sql:
            if self.namespace is None:
                return FakeResult()
            return FakeResult(row=self.namespace)
        if "SELECT role" in sql and "FROM namespace_member" in sql:
            return FakeResult(row={"role": self.role}) if self.role is not None else FakeResult()
        if "COUNT(*) AS count" in sql:
            return FakeResult(row={"count": len(self.members)})
        if "LEFT JOIN user_account" in sql:
            offset = int(bound.get("offset", 0))
            limit = int(bound.get("limit", len(self.members)))
            return FakeResult(rows=self.members[offset : offset + limit])
        if "SELECT user_id" in sql and "FROM namespace_member" in sql:
            return FakeResult(rows=[{"user_id": user_id} for user_id in self.existing_member_ids])
        if "FROM user_account" in sql:
            keyword = str(bound["keyword"]).strip("%").lower()
            limit = int(bound["limit"])
            rows = [
                row
                for row in self.users
                if row["status"] == "ACTIVE"
                and (
                    keyword in row["id"].lower()
                    or keyword in row["display_name"].lower()
                    or keyword in (row["email"] or "").lower()
                )
            ]
            return FakeResult(rows=rows[:limit])
        return FakeResult()


def namespace_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 10,
        "slug": "team-a",
        "display_name": "Team A",
        "status": "ACTIVE",
        "description": "Team namespace",
        "type": "TEAM",
        "avatar_url": None,
        "created_by": "owner",
        "created_at": datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return data


def member_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 101,
        "namespace_id": 10,
        "user_id": "owner",
        "display_name": "Owner User",
        "email": "owner@example.test",
        "role": "OWNER",
        "created_at": datetime(2026, 6, 10, 8, 5, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 10, 8, 6, tzinfo=UTC),
    }
    data.update(overrides)
    return data


def user_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "candidate-1",
        "display_name": "Candidate One",
        "email": "candidate@example.test",
        "status": "ACTIVE",
    }
    data.update(overrides)
    return data


def auth_user(user_id: str = "owner") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "Owner",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


@pytest.mark.anyio
async def test_list_namespace_members_requires_membership_and_returns_page() -> None:
    forbidden = FakeNamespaceMemberConnection(role=None)
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.membership.required") as exc_info:
        await list_namespace_members(FakeEngine(forbidden), slug="team-a", user_id="outsider", page=0, size=20)
    assert exc_info.value.status_code == 403

    connection = FakeNamespaceMemberConnection(
        role="MEMBER",
        members=[
            member_row(id=101, user_id="owner", role="OWNER"),
            member_row(id=102, user_id="member", display_name=None, email=None, role="MEMBER"),
        ],
    )

    response = await list_namespace_members(FakeEngine(connection), slug="team-a", user_id="member", page=0, size=20)

    assert response["total"] == 2
    assert response["page"] == 0
    assert response["size"] == 20
    assert response["items"][0]["displayName"] == "Owner User"
    assert response["items"][0]["createdAt"] == "2026-06-10T08:05:00Z"
    assert response["items"][1]["email"] is None
    assert connection.params[1] == {"namespace_id": 10, "user_id": "member"}


@pytest.mark.anyio
async def test_search_namespace_member_candidates_matches_java_boundaries() -> None:
    base_users = [
        user_row(id="candidate-1", display_name="Candidate One"),
        user_row(id="existing-user", display_name="Candidate Existing"),
        user_row(id="inactive-candidate", display_name="Candidate Inactive", status="DISABLED"),
        user_row(id="other", display_name="Other User", email="other@example.test"),
    ]

    connection = FakeNamespaceMemberConnection(role="ADMIN", users=base_users, existing_member_ids=["existing-user"])
    blank = await search_namespace_member_candidates(
        FakeEngine(connection),
        slug="team-a",
        search="   ",
        user_id="admin",
        size=10,
    )
    assert blank == []

    with pytest.raises(NamespaceMemberReadError, match="error.namespace.member.search.tooShort") as too_short:
        await search_namespace_member_candidates(FakeEngine(connection), slug="team-a", search=" c ", user_id="admin", size=10)
    assert too_short.value.status_code == 400

    candidates = await search_namespace_member_candidates(
        FakeEngine(connection),
        slug="team-a",
        search="candidate",
        user_id="admin",
        size=99,
    )
    assert candidates == [
        {
            "userId": "candidate-1",
            "displayName": "Candidate One",
            "email": "candidate@example.test",
            "status": "ACTIVE",
        }
    ]
    assert connection.params[-1]["limit"] == 20


@pytest.mark.anyio
async def test_search_namespace_member_candidates_enforces_namespace_rules() -> None:
    global_ns = FakeNamespaceMemberConnection(namespace=namespace_row(type="GLOBAL", slug="global"))
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.system.immutable") as immutable:
        await search_namespace_member_candidates(FakeEngine(global_ns), slug="global", search="candidate", user_id="owner", size=10)
    assert immutable.value.status_code == 400

    non_member = FakeNamespaceMemberConnection(role=None)
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.membership.required") as no_membership:
        await search_namespace_member_candidates(FakeEngine(non_member), slug="team-a", search="candidate", user_id="outsider", size=10)
    assert no_membership.value.status_code == 403

    member = FakeNamespaceMemberConnection(role="MEMBER")
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.admin.required") as not_admin:
        await search_namespace_member_candidates(FakeEngine(member), slug="team-a", search="candidate", user_id="member", size=10)
    assert not_admin.value.status_code == 403

    frozen = FakeNamespaceMemberConnection(namespace=namespace_row(status="FROZEN"), role="OWNER")
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.readonly") as readonly:
        await search_namespace_member_candidates(FakeEngine(frozen), slug="team-a", search="candidate", user_id="owner", size=10)
    assert readonly.value.status_code == 400


def test_namespace_member_routes_use_java_envelopes() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.namespace_member_reader = lambda slug, user_id, page, size: {
        "items": [{"id": 101, "namespaceId": 10, "userId": "owner", "role": "OWNER"}],
        "total": 1,
        "page": page,
        "size": size,
    }
    app.state.namespace_member_candidate_reader = lambda slug, search, user_id, size: [
        {"userId": "candidate-1", "displayName": search, "email": "candidate@example.test", "status": "ACTIVE"}
    ]
    client = TestClient(app)

    assert client.get("/api/v1/namespaces/team-a/members").status_code == 401

    members = client.get(
        "/api/web/namespaces/team-a/members?page=2&size=5",
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "member-list"},
    )
    assert members.status_code == 200
    assert members.json()["requestId"] == "member-list"
    assert members.json()["data"]["page"] == 2

    candidates = client.get(
        "/api/v1/namespaces/team-a/member-candidates?search=Candidate&size=25",
        headers={"X-Mock-User-Id": "owner"},
    )
    assert candidates.status_code == 200
    assert candidates.json()["data"][0]["displayName"] == "Candidate"
