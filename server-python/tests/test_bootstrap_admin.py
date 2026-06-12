from __future__ import annotations

from typing import Any

import pytest

from app.bootstrap import initialize_bootstrap_admin


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def mappings(self) -> FakeMappings:
        return FakeMappings([] if self.row is None else [self.row])


class FakeTransaction:
    def __init__(self, connection: "FakeBootstrapConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeBootstrapConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeBootstrapConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeBootstrapConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.credentials: dict[str, dict[str, Any]] = {}
        self.roles: dict[str, int] = {"SUPER_ADMIN": 7}
        self.role_bindings: list[dict[str, Any]] = []
        self.namespaces: dict[str, dict[str, Any]] = {"global": {"id": 1, "slug": "global"}}
        self.namespace_members: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM local_credential" in sql and "LOWER(username)" in sql:
            username = str(bound["username"]).lower()
            row = next((row for row in self.credentials.values() if row["username"].lower() == username), None)
            return FakeResult(row.copy() if row else None)
        if "FROM user_account" in sql and "WHERE id = :user_id" in sql:
            row = self.users.get(str(bound["user_id"]))
            return FakeResult(row.copy() if row else None)
        if "INSERT INTO user_account" in sql:
            self.users[str(bound["id"])] = {
                "id": str(bound["id"]),
                "display_name": str(bound["display_name"]),
                "email": str(bound["email"]),
                "avatar_url": bound["avatar_url"],
                "status": str(bound["status"]),
            }
            return FakeResult()
        if "UPDATE user_account" in sql:
            user = self.users[str(bound["user_id"])]
            user["display_name"] = str(bound["display_name"])
            user["email"] = str(bound["email"])
            return FakeResult()
        if "INSERT INTO local_credential" in sql:
            self.credentials[str(bound["user_id"])] = {
                "user_id": str(bound["user_id"]),
                "username": str(bound["username"]),
                "password_hash": str(bound["password_hash"]),
            }
            return FakeResult()
        if "FROM role" in sql and "WHERE code = :code" in sql:
            role_id = self.roles.get(str(bound["code"]))
            return FakeResult({"id": role_id, "code": bound["code"]} if role_id is not None else None)
        if "FROM user_role_binding" in sql:
            row = next(
                (
                    row
                    for row in self.role_bindings
                    if row["user_id"] == bound["user_id"] and row["role_id"] == bound["role_id"]
                ),
                None,
            )
            return FakeResult(row.copy() if row else None)
        if "INSERT INTO user_role_binding" in sql:
            self.role_bindings.append({"user_id": bound["user_id"], "role_id": bound["role_id"]})
            return FakeResult()
        if "FROM namespace" in sql and "slug = 'global'" in sql:
            return FakeResult(self.namespaces["global"].copy())
        if "FROM namespace_member" in sql:
            row = next(
                (
                    row
                    for row in self.namespace_members
                    if row["namespace_id"] == bound["namespace_id"] and row["user_id"] == bound["user_id"]
                ),
                None,
            )
            return FakeResult(row.copy() if row else None)
        if "INSERT INTO namespace_member" in sql:
            self.namespace_members.append(
                {"namespace_id": bound["namespace_id"], "user_id": bound["user_id"], "role": bound["role"]}
            )
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def fake_hash(password: str) -> str:
    return f"hash:{password}"


@pytest.mark.anyio
async def test_bootstrap_admin_seeds_java_compatible_account_role_and_membership() -> None:
    connection = FakeBootstrapConnection()

    await initialize_bootstrap_admin(
        FakeEngine(connection),
        environ={"BOOTSTRAP_ADMIN_ENABLED": "true"},
        password_hasher=fake_hash,
    )

    assert connection.users["docker-admin"] == {
        "id": "docker-admin",
        "display_name": "Admin",
        "email": "admin@skillhub.local",
        "avatar_url": None,
        "status": "ACTIVE",
    }
    assert connection.credentials["docker-admin"] == {
        "user_id": "docker-admin",
        "username": "admin",
        "password_hash": "hash:ChangeMe!2026",
    }
    assert connection.role_bindings == [{"user_id": "docker-admin", "role_id": 7}]
    assert connection.namespace_members == [{"namespace_id": 1, "user_id": "docker-admin", "role": "OWNER"}]


@pytest.mark.anyio
async def test_bootstrap_admin_is_disabled_by_default() -> None:
    connection = FakeBootstrapConnection()

    await initialize_bootstrap_admin(FakeEngine(connection), environ={}, password_hasher=fake_hash)

    assert connection.users == {}
    assert connection.credentials == {}


@pytest.mark.anyio
async def test_bootstrap_admin_skips_when_username_belongs_to_another_user() -> None:
    connection = FakeBootstrapConnection()
    connection.credentials["other-user"] = {
        "user_id": "other-user",
        "username": "admin",
        "password_hash": "hash:Existing123!",
    }

    await initialize_bootstrap_admin(
        FakeEngine(connection),
        environ={"BOOTSTRAP_ADMIN_ENABLED": "true"},
        password_hasher=fake_hash,
    )

    assert "docker-admin" not in connection.users
    assert connection.role_bindings == []
