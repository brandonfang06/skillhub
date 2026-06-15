from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.users import (
    AdminUserError,
    list_admin_users,
    trigger_admin_password_reset,
    update_admin_user_role,
    update_admin_user_status,
)
from app.main import create_app


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


class FakeTransaction:
    def __init__(self, connection: "FakeAdminUserConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeAdminUserConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeAdminUserConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeAdminUserConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {
            "user-1": user_row("user-1", "Alice Admin", "alice@example.test", "ACTIVE", 3),
            "user-2": user_row("user-2", "Bob User", "bob@example.test", "ACTIVE", 2),
            "user-3": user_row("user-3", "Disabled User", "disabled@example.test", "DISABLED", 1),
            "user-4": user_row("user-4", "No Credential", "no-credential@example.test", "ACTIVE", 4),
            "user-5": user_row("user-5", "No Email", "", "ACTIVE", 5),
            "builtin-skill-publisher": user_row(
                "builtin-skill-publisher",
                "Built-in Skill Publisher",
                "builtin-skill-publisher@system.invalid",
                "ACTIVE",
                6,
                system_account=True,
            ),
        }
        self.local_credentials = {"user-1", "user-2", "user-3", "user-5", "builtin-skill-publisher"}
        self.reset_requests: list[dict[str, Any]] = [
            {
                "user_id": "user-2",
                "email": "bob@example.test",
                "code_hash": "$2a$old",
                "expires_at": datetime(2026, 6, 10, 8, 30, tzinfo=UTC),
                "consumed_at": None,
                "requested_by_admin": True,
                "requested_by_user_id": "old-admin",
            }
        ]
        self.roles = {"USER_ADMIN": 10, "SUPER_ADMIN": 11, "SKILL_ADMIN": 12}
        self.user_roles: dict[str, list[str]] = {"user-1": ["USER_ADMIN"], "user-3": ["SKILL_ADMIN", "USER_ADMIN"]}
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "COUNT(*) AS count" in sql and "FROM user_account" in sql:
            return FakeResult(row={"count": len(self._filtered_users(bound))})
        if "FROM user_account" in sql and "ORDER BY created_at DESC" in sql:
            rows = self._filtered_users(bound)
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            offset = int(bound.get("offset", 0))
            limit = int(bound.get("limit", len(rows)))
            return FakeResult(rows=rows[offset : offset + limit])
        if "FROM user_account" in sql and "WHERE id = :user_id" in sql:
            row = self.users.get(str(bound["user_id"]))
            return FakeResult(row=row) if row else FakeResult()
        if "FROM local_credential" in sql:
            user_id = str(bound["user_id"])
            return FakeResult(row={"user_id": user_id}) if user_id in self.local_credentials else FakeResult()
        if "UPDATE password_reset_request" in sql:
            for row in self.reset_requests:
                if row["user_id"] == bound["user_id"] and row["consumed_at"] is None:
                    row["consumed_at"] = bound["consumed_at"]
            return FakeResult()
        if "INSERT INTO password_reset_request" in sql:
            self.reset_requests.append(
                {
                    "user_id": bound["user_id"],
                    "email": bound["email"],
                    "code_hash": bound["code_hash"],
                    "expires_at": bound["expires_at"],
                    "consumed_at": None,
                    "requested_by_admin": bound["requested_by_admin"],
                    "requested_by_user_id": bound["requested_by_user_id"],
                }
            )
            return FakeResult()
        if "FROM user_role_binding" in sql and "r.code" in sql:
            rows: list[dict[str, Any]] = []
            for user_id in bound["user_ids"]:
                rows.extend({"user_id": user_id, "code": code} for code in self.user_roles.get(user_id, []))
            return FakeResult(rows=rows)
        if "FROM role" in sql and "WHERE code = :role_code" in sql:
            role_id = self.roles.get(str(bound["role_code"]))
            return FakeResult(row={"id": role_id, "code": bound["role_code"]}) if role_id else FakeResult()
        if "DELETE FROM user_role_binding" in sql:
            self.user_roles[str(bound["user_id"])] = []
            return FakeResult()
        if "INSERT INTO user_role_binding" in sql:
            role_code = next(code for code, role_id in self.roles.items() if role_id == int(bound["role_id"]))
            self.user_roles.setdefault(str(bound["user_id"]), []).append(role_code)
            return FakeResult()
        if "UPDATE user_account" in sql:
            self.users[str(bound["user_id"])]["status"] = bound["status"]
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")

    def _filtered_users(self, bound: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.users.values())
        status = bound.get("status")
        if status:
            rows = [row for row in rows if row["status"] == status]
        search = str(bound.get("search") or "").replace("%", "").lower()
        if search:
            rows = [
                row
                for row in rows
                if search in row["id"].lower()
                or search in row["display_name"].lower()
                or search in str(row["email"]).lower()
            ]
        return [row.copy() for row in rows]


def user_row(
    user_id: str,
    display_name: str,
    email: str,
    status: str,
    day: int,
    *,
    system_account: bool = False,
) -> dict[str, Any]:
    return {
        "id": user_id,
        "display_name": display_name,
        "email": email,
        "status": status,
        "system_account": system_account,
        "created_at": datetime(2026, 6, day, 8, 0, tzinfo=UTC),
    }


def auth_user(user_id: str, roles: list[str]) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles,
    }


@pytest.mark.anyio
async def test_list_admin_users_filters_sorts_and_adds_default_user_role() -> None:
    connection = FakeAdminUserConnection()

    response = await list_admin_users(
        FakeEngine(connection),
        search="example.test",
        status="active",
        page=0,
        size=20,
        platform_roles=["USER_ADMIN"],
    )

    assert response["total"] == 3
    assert [item["id"] for item in response["items"]] == ["user-4", "user-1", "user-2"]
    assert response["items"][0]["platformRoles"] == ["USER"]
    assert response["items"][1]["platformRoles"] == ["USER_ADMIN"]
    assert response["items"][2]["platformRoles"] == ["USER"]
    assert response["page"] == 0
    assert response["size"] == 20


@pytest.mark.anyio
async def test_update_role_replaces_bindings_and_protects_super_admin_assignment() -> None:
    connection = FakeAdminUserConnection()

    response = await update_admin_user_role(
        FakeEngine(connection),
        user_id="user-2",
        role="skill_admin",
        actor_platform_roles=["SUPER_ADMIN"],
    )

    assert response == {"userId": "user-2", "role": "SKILL_ADMIN", "status": "ACTIVE"}
    assert connection.user_roles["user-2"] == ["SKILL_ADMIN"]

    default_role = await update_admin_user_role(
        FakeEngine(connection),
        user_id="user-2",
        role="USER",
        actor_platform_roles=["USER_ADMIN"],
    )

    assert default_role == {"userId": "user-2", "role": "USER", "status": "ACTIVE"}
    assert connection.user_roles["user-2"] == []

    with pytest.raises(AdminUserError, match="error.admin.user.role.superAdmin.assignDenied") as forbidden:
        await update_admin_user_role(
            FakeEngine(connection),
            user_id="user-2",
            role="SUPER_ADMIN",
            actor_platform_roles=["USER_ADMIN"],
        )
    assert forbidden.value.status_code == 403


@pytest.mark.anyio
async def test_update_role_and_status_reject_system_accounts() -> None:
    connection = FakeAdminUserConnection()

    with pytest.raises(AdminUserError, match="error.admin.user.systemAccount.immutable") as role_forbidden:
        await update_admin_user_role(
            FakeEngine(connection),
            user_id="builtin-skill-publisher",
            role="SKILL_ADMIN",
            actor_platform_roles=["SUPER_ADMIN"],
        )
    assert role_forbidden.value.status_code == 403
    assert connection.user_roles.get("builtin-skill-publisher") is None

    with pytest.raises(AdminUserError, match="error.admin.user.systemAccount.immutable") as status_forbidden:
        await update_admin_user_status(FakeEngine(connection), user_id="builtin-skill-publisher", status="DISABLED")
    assert status_forbidden.value.status_code == 403
    assert connection.users["builtin-skill-publisher"]["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_update_status_accepts_only_manageable_statuses() -> None:
    connection = FakeAdminUserConnection()

    response = await update_admin_user_status(FakeEngine(connection), user_id="user-2", status="disabled")

    assert response == {"userId": "user-2", "role": None, "status": "DISABLED"}
    assert connection.users["user-2"]["status"] == "DISABLED"

    with pytest.raises(AdminUserError, match="error.admin.user.status.unsupported"):
        await update_admin_user_status(FakeEngine(connection), user_id="user-2", status="PENDING")


@pytest.mark.anyio
async def test_trigger_admin_password_reset_consumes_old_request_and_creates_admin_request() -> None:
    connection = FakeAdminUserConnection()

    result = await trigger_admin_password_reset(
        FakeEngine(connection),
        user_id="user-2",
        admin_user_id="admin-1",
        actor_platform_roles=["USER_ADMIN"],
        code_generator=lambda: "123456",
    )

    assert result is None
    assert connection.reset_requests[0]["consumed_at"] is not None
    created = connection.reset_requests[-1]
    assert created["user_id"] == "user-2"
    assert created["email"] == "bob@example.test"
    assert created["code_hash"].startswith("$2")
    assert created["code_hash"] != "123456"
    assert created["requested_by_admin"] is True
    assert created["requested_by_user_id"] == "admin-1"


@pytest.mark.anyio
async def test_trigger_admin_password_reset_matches_java_error_cases() -> None:
    connection = FakeAdminUserConnection()

    with pytest.raises(AdminUserError, match="error.admin.user.notFound") as missing:
        await trigger_admin_password_reset(
            FakeEngine(connection),
            user_id="missing",
            admin_user_id="admin-1",
            actor_platform_roles=["USER_ADMIN"],
        )
    assert missing.value.status_code == 404

    for user_id in ["user-3", "user-4", "user-5"]:
        with pytest.raises(AdminUserError, match="error.auth.password.reset.not.eligible") as ineligible:
            await trigger_admin_password_reset(
                FakeEngine(connection),
                user_id=user_id,
                admin_user_id="admin-1",
                actor_platform_roles=["USER_ADMIN"],
            )
        assert ineligible.value.status_code == 400

    with pytest.raises(AdminUserError, match="error.admin.userAdminRequired") as forbidden:
        await trigger_admin_password_reset(
            FakeEngine(connection),
            user_id="user-2",
            admin_user_id="regular",
            actor_platform_roles=["USER"],
        )
    assert forbidden.value.status_code == 403


@pytest.mark.anyio
async def test_trigger_admin_password_reset_rejects_system_account_before_credential_lookup() -> None:
    connection = FakeAdminUserConnection()

    with pytest.raises(AdminUserError, match="error.auth.password.reset.not.eligible") as ineligible:
        await trigger_admin_password_reset(
            FakeEngine(connection),
            user_id="builtin-skill-publisher",
            admin_user_id="admin-1",
            actor_platform_roles=["SUPER_ADMIN"],
            code_generator=lambda: "123456",
            code_hasher=lambda code: f"hashed-{code}",
        )

    assert ineligible.value.status_code == 400
    assert all(row["user_id"] != "builtin-skill-publisher" for row in connection.reset_requests)


def test_admin_user_routes_use_java_envelopes_and_admin_roles() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(
        user_id,
        ["USER_ADMIN"] if user_id == "admin" else ["USER"],
    )
    app.state.admin_user_reader = lambda payload, user: {"items": [{"id": "user-1"}], "total": 1, "page": 0, "size": 20}
    app.state.admin_user_role_writer = lambda user_id, payload, user: {
        "userId": user_id,
        "role": payload["role"],
        "status": "ACTIVE",
    }
    app.state.admin_user_status_writer = lambda user_id, payload, user: {
        "userId": user_id,
        "role": None,
        "status": payload["status"],
    }
    app.state.admin_user_password_reset_writer = lambda user_id, user: None
    client = TestClient(app)

    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.get("/api/v1/admin/users", headers={"X-Mock-User-Id": "user"}).status_code == 403

    listed = client.get("/api/v1/admin/users", headers={"X-Mock-User-Id": "admin"})
    assert listed.status_code == 200
    assert listed.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert listed.json()["data"]["items"] == [{"id": "user-1"}]

    role = client.put(
        "/api/v1/admin/users/user-1/role",
        json={"role": "SKILL_ADMIN"},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert role.status_code == 200
    assert role.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert role.json()["data"]["role"] == "SKILL_ADMIN"

    disabled = client.post("/api/v1/admin/users/user-1/disable", headers={"X-Mock-User-Id": "admin"})
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "DISABLED"

    reset = client.post("/api/v1/admin/users/user-1/password-reset", headers={"X-Mock-User-Id": "admin"})
    assert reset.status_code == 200
    assert reset.json()["msg"] == "\u5982\u679c\u8d26\u53f7\u7b26\u5408\u6761\u4ef6\uff0c\u5bc6\u7801\u91cd\u7f6e\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001\u3002"
    assert reset.json()["data"] is None
