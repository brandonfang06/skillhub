from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.admin_namespace.read_repository import (
    JAVA_INT_MAX,
    AdminNamespaceReadError,
    _permissions,
    list_admin_namespaces,
    normalize_candidate_size,
    normalize_page,
    normalize_page_size,
    normalize_search,
)
from app.main import create_app


def auth_user(
    user_id: str = "admin",
    roles: list[str] | None = None,
    *,
    provider: str = "mock",
) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": provider,
        "platformRoles": roles if roles is not None else ["SUPER_ADMIN"],
    }


def admin_namespace(slug: str = "team-a") -> dict[str, object]:
    return {
        "id": 10,
        "slug": slug,
        "displayName": "Team A",
        "status": "ACTIVE",
        "description": "Team namespace",
        "type": "TEAM",
        "avatarUrl": None,
        "createdBy": "owner",
        "createdAt": "2026-08-12T00:00:00Z",
        "updatedAt": "2026-08-12T01:00:00Z",
        "stats": {"memberCount": 2, "skillCount": 5},
        "permissions": {
            "currentUserRole": None,
            "platformOverride": True,
            "immutable": False,
            "canManageMembers": True,
            "canGovernNamespace": True,
            "canPublish": True,
            "canTransferOwnership": True,
            "canFreeze": True,
            "canUnfreeze": False,
            "canArchive": True,
            "canRestore": False,
        },
    }


def configured_app() -> object:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(
        user_id,
        ["SUPER_ADMIN"] if user_id == "admin" else ["USER_ADMIN"],
    )
    app.state.auth_bearer_reader = lambda token: (
        auth_user("token-admin", provider="api_token") if token == "valid" else None
    )
    app.state.admin_namespace_list_reader = lambda **kwargs: {
        "items": [admin_namespace()],
        "total": 1,
        "page": kwargs["page"],
        "size": kwargs["size"],
        "stats": {"total": 3, "active": 1, "frozen": 1, "archived": 1},
    }
    app.state.admin_namespace_detail_reader = lambda **kwargs: admin_namespace(
        kwargs["slug"]
    )
    app.state.admin_namespace_member_reader = lambda **kwargs: {
        "items": [
            {
                "id": 1,
                "namespaceId": 10,
                "userId": "owner",
                "displayName": "Owner",
                "email": "owner@example.test",
                "role": "OWNER",
                "createdAt": "2026-08-12T00:00:00Z",
                "updatedAt": "2026-08-12T00:00:00Z",
            }
        ],
        "total": 1,
        "page": kwargs["page"],
        "size": kwargs["size"],
    }
    app.state.admin_namespace_candidate_reader = lambda **kwargs: [
        {
            "userId": "candidate",
            "displayName": "Candidate",
            "email": "candidate@example.test",
            "status": "ACTIVE",
        }
    ]
    return app


def test_admin_namespace_read_route_inventory_is_v1_only() -> None:
    app = create_app()
    routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/api/v1/admin/namespaces") and method == "GET"
    }

    assert routes == {
        ("GET", "/api/v1/admin/namespaces"),
        ("GET", "/api/v1/admin/namespaces/{slug}"),
        ("GET", "/api/v1/admin/namespaces/{slug}/members"),
        ("GET", "/api/v1/admin/namespaces/{slug}/member-candidates"),
    }
    assert not any("/api/web/admin/namespaces" in path for _, path in routes)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespaces",
        "/api/v1/admin/namespaces/team-a",
        "/api/v1/admin/namespaces/team-a/members",
        "/api/v1/admin/namespaces/team-a/member-candidates?search=ca",
    ],
)
def test_admin_namespace_routes_enforce_session_super_admin_policy(path: str) -> None:
    app = configured_app()
    client = TestClient(app)

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Mock-User-Id": "user-admin"}).status_code == 403

    bearer = client.get(path, headers={"Authorization": "Bearer valid"})
    assert bearer.status_code == 403
    assert bearer.json()["msg"] == "error.apiToken.endpoint.unsupported"
    assert bearer.json()["data"]["args"] == [path.split("?", 1)[0]]

    invalid = client.get(path, headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "error.auth.required"

    allowed = client.get(
        path, headers={"X-Mock-User-Id": "admin", "X-Request-Id": "admin-ns"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["requestId"] == "admin-ns"


def test_admin_namespace_routes_normalize_pages_and_keep_java_envelopes() -> None:
    app = configured_app()
    client = TestClient(app)
    headers = {"X-Mock-User-Id": "admin"}

    response = client.get(
        "/api/v1/admin/namespaces?keyword=TEAM&status=active&type=team&page=-2&size=999",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["page"] == 0
    assert response.json()["data"]["size"] == 100
    assert (
        response.json()["data"]["items"][0]["permissions"]["platformOverride"] is True
    )

    members = client.get(
        "/api/v1/admin/namespaces/team-a/members?page=-1&size=0",
        headers=headers,
    )
    assert members.status_code == 200
    assert members.json()["data"]["page"] == 0
    assert members.json()["data"]["size"] == 20

    candidates = client.get(
        "/api/v1/admin/namespaces/team-a/member-candidates?search=ca&size=99",
        headers=headers,
    )
    assert candidates.status_code == 200
    assert candidates.json()["data"][0]["status"] == "ACTIVE"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespaces",
        "/api/v1/admin/namespaces/team-a/members",
    ],
)
def test_admin_namespace_routes_reject_pages_above_java_int_max(path: str) -> None:
    app = configured_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        f"{path}?page={JAVA_INT_MAX + 1}&size=100",
        headers={"X-Mock-User-Id": "admin"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.pagination.page.invalid"


def test_admin_namespace_list_accepts_browser_session_principal() -> None:
    app = configured_app()
    app.state.local_auth_login = lambda payload: auth_user("admin")
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "admin", "password": "Abcd123!"},
    )
    response = client.get("/api/v1/admin/namespaces")

    assert login.status_code == 200
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["slug"] == "team-a"


def test_admin_namespace_openapi_exposes_typed_read_contracts() -> None:
    schema = create_app().openapi()
    list_operation = schema["paths"]["/api/v1/admin/namespaces"]["get"]
    response_schema = list_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    assert response_schema["$ref"].endswith("AdminNamespaceListEnvelope")
    assert schema["paths"]["/api/v1/admin/namespaces/{slug}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]["$ref"].endswith(
        "AdminNamespaceDetailEnvelope"
    )
    assert schema["paths"]["/api/v1/admin/namespaces/{slug}/members"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "AdminNamespaceMemberPageEnvelope"
    )
    assert schema["paths"]["/api/v1/admin/namespaces/{slug}/member-candidates"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "AdminNamespaceCandidateListEnvelope"
    )

    summary = schema["components"]["schemas"]["AdminNamespaceSummary"]
    assert set(summary["required"]) == {
        "id",
        "slug",
        "displayName",
        "status",
        "description",
        "type",
        "avatarUrl",
        "createdBy",
        "createdAt",
        "updatedAt",
        "stats",
        "permissions",
    }


@pytest.mark.parametrize(
    ("namespace_type", "status", "expected"),
    [
        (
            "GLOBAL",
            "ACTIVE",
            (False, False, False, False, False, False, False, False, True),
        ),
        ("TEAM", "ACTIVE", (True, True, True, True, True, False, True, False, False)),
        (
            "TEAM",
            "FROZEN",
            (False, True, False, False, False, True, True, False, False),
        ),
        (
            "TEAM",
            "ARCHIVED",
            (False, True, False, False, False, False, False, True, False),
        ),
    ],
)
def test_admin_namespace_capability_matrix(
    namespace_type: str,
    status: str,
    expected: tuple[bool, ...],
) -> None:
    permissions = _permissions(
        namespace_type=namespace_type, status=status, current_user_role="MEMBER"
    )
    actual = (
        permissions["canManageMembers"],
        permissions["canGovernNamespace"],
        permissions["canPublish"],
        permissions["canTransferOwnership"],
        permissions["canFreeze"],
        permissions["canUnfreeze"],
        permissions["canArchive"],
        permissions["canRestore"],
        permissions["immutable"],
    )
    assert actual == expected
    assert permissions["currentUserRole"] == "MEMBER"
    assert permissions["platformOverride"] is True


def test_admin_namespace_input_normalization() -> None:
    assert normalize_page(-10) == 0
    assert normalize_page(JAVA_INT_MAX) == JAVA_INT_MAX
    assert normalize_page_size(0) == 20
    assert normalize_page_size(999) == 100
    assert normalize_candidate_size(0) == 10
    assert normalize_candidate_size(999) == 20
    assert normalize_search("  ") is None
    assert normalize_search(" Alice ") == "Alice"
    with pytest.raises(
        AdminNamespaceReadError, match="error.namespace.member.search.tooShort"
    ):
        normalize_search("a")
    with pytest.raises(
        AdminNamespaceReadError, match="error.pagination.page.invalid"
    ) as too_large:
        normalize_page(JAVA_INT_MAX + 1)
    assert too_large.value.status_code == 400


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one(self) -> dict[str, Any]:
        return self.rows[0]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return int(self.rows[0]["count"])


class FakeConnect:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(
        self, statement: object, params: dict[str, Any] | None = None
    ) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "admin-namespace-page-count" in sql:
            return FakeResult([{"count": 1}])
        if "admin-namespace-list-stats" in sql:
            return FakeResult([{"total": 3, "active": 1, "frozen": 1, "archived": 1}])
        if "admin-namespace-page" in sql:
            return FakeResult(
                [
                    {
                        "id": 10,
                        "slug": "team-a",
                        "display_name": "Team A",
                        "status": "ACTIVE",
                        "description": "Team namespace",
                        "type": "TEAM",
                        "avatar_url": None,
                        "created_by": "owner",
                        "created_at": datetime(2026, 8, 12, tzinfo=UTC),
                        "updated_at": datetime(2026, 8, 13, tzinfo=UTC),
                        "member_count": 501,
                        "skill_count": 7,
                        "current_user_role": None,
                    }
                ]
            )
        raise AssertionError(sql)


@pytest.mark.anyio
async def test_list_admin_namespaces_bulk_loads_counts_and_role_without_n_plus_one() -> (
    None
):
    connection = FakeConnection()

    response = await list_admin_namespaces(
        FakeEngine(connection),
        keyword=" TEAM ",
        status="active",
        namespace_type="team",
        page=-1,
        size=1000,
        actor_user_id="super-admin",
    )

    assert response["stats"] == {"total": 3, "active": 1, "frozen": 1, "archived": 1}
    assert response["items"][0]["stats"] == {"memberCount": 501, "skillCount": 7}
    assert response["items"][0]["permissions"]["currentUserRole"] is None
    assert response["page"] == 0
    assert response["size"] == 100
    assert len(connection.statements) == 3
    page_sql = next(
        sql for sql in connection.statements if "admin-namespace-page */" in sql
    )
    assert "COUNT(*)" in page_sql
    assert "FROM namespace_member" in page_sql
    assert "FROM skill" in page_sql
    assert "actor_nm.user_id = :actor_user_id" in page_sql
    assert "ORDER BY n.updated_at DESC, n.slug ASC" in page_sql
    assert connection.params[-1]["keyword"] == "%team%"


@pytest.mark.anyio
async def test_list_admin_namespaces_rejects_invalid_filters() -> None:
    connection = FakeConnection()
    with pytest.raises(
        AdminNamespaceReadError, match="error.namespace.status.invalid"
    ) as status_error:
        await list_admin_namespaces(
            FakeEngine(connection),
            keyword=None,
            status="deleted",
            namespace_type=None,
            page=0,
            size=20,
            actor_user_id="admin",
        )
    assert status_error.value.status_code == 400

    with pytest.raises(
        AdminNamespaceReadError, match="error.namespace.type.invalid"
    ) as type_error:
        await list_admin_namespaces(
            FakeEngine(connection),
            keyword=None,
            status=None,
            namespace_type="personal",
            page=0,
            size=20,
            actor_user_id="admin",
        )
    assert type_error.value.status_code == 400
    assert connection.statements == []
