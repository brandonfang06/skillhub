from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace.mutations import (
    NamespaceMutationError,
    archive_namespace,
    create_namespace,
    delete_namespace,
    freeze_namespace,
    restore_namespace,
    unfreeze_namespace,
    update_namespace,
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


class FakeTransaction:
    def __init__(self, connection: "FakeNamespaceMutationConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeNamespaceMutationConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeNamespaceMutationConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeNamespaceMutationConnection:
    def __init__(
        self,
        *,
        namespaces: dict[str, dict[str, Any]] | None = None,
        members: dict[int, dict[str, str]] | None = None,
        dependencies: set[int] | None = None,
    ) -> None:
        self.namespaces = namespaces or {"team-a": namespace_row(id=10, slug="team-a")}
        self.members = members or {10: {"owner": "OWNER", "admin": "ADMIN", "member": "MEMBER"}}
        self.dependencies = dependencies or set()
        self.next_namespace_id = max((int(row["id"]) for row in self.namespaces.values()), default=10)
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.audit_rows: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "SELECT" in sql and "COUNT(*) FROM skill" in sql:
            namespace_id = int(bound["namespace_ids"][0])
            has_deps = namespace_id in self.dependencies
            return FakeResult(
                row={
                    "namespace_id": namespace_id,
                    "skill_count": 1 if has_deps else 0,
                    "review_task_count": 0,
                    "promotion_request_count": 0,
                }
            )
        if "FROM namespace n" in sql or "FROM namespace" in sql and "WHERE slug" in sql:
            row = self.namespaces.get(str(bound["slug"]))
            return FakeResult(row=row.copy()) if row else FakeResult()
        if "INSERT INTO namespace " in sql:
            slug = str(bound["slug"])
            self.next_namespace_id += 1
            self.namespaces[slug] = namespace_row(
                id=self.next_namespace_id,
                slug=slug,
                display_name=bound["display_name"],
                description=bound.get("description"),
                created_by=bound["created_by"],
            )
            self.members[self.next_namespace_id] = {}
            return FakeResult(row=self.namespaces[slug].copy())
        if "INSERT INTO namespace_member" in sql:
            self.members.setdefault(int(bound["namespace_id"]), {})[str(bound["user_id"])] = str(bound["role"])
            return FakeResult()
        if "SELECT role" in sql and "FROM namespace_member" in sql:
            role = self.members.get(int(bound["namespace_id"]), {}).get(str(bound["user_id"]))
            return FakeResult(row={"role": role}) if role else FakeResult()
        if "UPDATE namespace" in sql:
            row = self._namespace_by_id(int(bound["namespace_id"]))
            if "display_name" in bound:
                row["display_name"] = bound["display_name"]
            if "description" in bound:
                row["description"] = bound["description"]
            if "status" in bound:
                row["status"] = bound["status"]
            row["updated_at"] = datetime(2026, 6, 10, 9, 30, tzinfo=UTC)
            return FakeResult(row=row.copy())
        if "DELETE FROM namespace_member" in sql:
            self.members.pop(int(bound["namespace_id"]), None)
            return FakeResult()
        if "DELETE FROM namespace" in sql:
            row = self._namespace_by_id(int(bound["namespace_id"]))
            self.namespaces.pop(str(row["slug"]), None)
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            self.audit_rows.append(bound.copy())
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")

    def _namespace_by_id(self, namespace_id: int) -> dict[str, Any]:
        for row in self.namespaces.values():
            if int(row["id"]) == namespace_id:
                return row
        raise AssertionError(f"unknown namespace id {namespace_id}")


def namespace_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 10,
        "slug": "team-a",
        "display_name": "Team A",
        "status": "ACTIVE",
        "description": "Team namespace",
        "type": "TEAM",
        "avatar_url": "",
        "created_by": "owner",
        "created_at": datetime(2026, 6, 10, 8, 5, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 10, 8, 6, tzinfo=UTC),
    }
    data.update(overrides)
    return data


def auth_user(user_id: str = "owner", roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["USER"],
    }


@pytest.mark.anyio
async def test_create_namespace_requires_platform_role_and_creates_owner_member() -> None:
    connection = FakeNamespaceMutationConnection(namespaces={}, members={})

    created = await create_namespace(
        FakeEngine(connection),
        slug="team-b",
        display_name="Team B",
        description="new team",
        actor_user_id="creator",
        platform_roles=["SKILL_ADMIN"],
    )

    assert created["slug"] == "team-b"
    assert created["displayName"] == "Team B"
    assert created["type"] == "TEAM"
    assert created["status"] == "ACTIVE"
    assert connection.members[int(created["id"])] == {"creator": "OWNER"}

    with pytest.raises(NamespaceMutationError, match="error.namespace.create.platformAdminRequired") as forbidden:
        await create_namespace(
            FakeEngine(FakeNamespaceMutationConnection(namespaces={}, members={})),
            slug="team-c",
            display_name="Team C",
            description=None,
            actor_user_id="user",
            platform_roles=["USER"],
        )
    assert forbidden.value.status_code == 403

    with pytest.raises(NamespaceMutationError, match="error.slug.reserved"):
        await create_namespace(
            FakeEngine(FakeNamespaceMutationConnection(namespaces={}, members={})),
            slug="admin",
            display_name="Admin",
            description=None,
            actor_user_id="creator",
            platform_roles=["SUPER_ADMIN"],
        )


@pytest.mark.anyio
async def test_update_and_delete_namespace_match_java_boundaries() -> None:
    connection = FakeNamespaceMutationConnection(dependencies={20}, namespaces={
        "team-a": namespace_row(id=10, slug="team-a"),
        "team-deps": namespace_row(id=20, slug="team-deps"),
    }, members={10: {"admin": "ADMIN", "owner": "OWNER"}, 20: {"owner": "OWNER"}})

    updated = await update_namespace(
        FakeEngine(connection),
        slug="team-a",
        display_name="Team A Updated",
        description="updated",
        actor_user_id="admin",
    )

    assert updated["displayName"] == "Team A Updated"
    assert updated["description"] == "updated"

    with pytest.raises(NamespaceMutationError, match="error.namespace.delete.hasDependencies") as deps:
        await delete_namespace(FakeEngine(connection), slug="team-deps", actor_user_id="owner")
    assert deps.value.status_code == 400

    deleted = await delete_namespace(FakeEngine(connection), slug="team-a", actor_user_id="owner")
    assert deleted == {"message": "Namespace deleted successfully"}
    assert "team-a" not in connection.namespaces
    assert 10 not in connection.members


@pytest.mark.anyio
async def test_super_admin_can_delete_dependency_free_team_without_membership() -> None:
    connection = FakeNamespaceMutationConnection(
        namespaces={"team-a": namespace_row(id=10, slug="team-a")},
        members={10: {}},
    )

    deleted = await delete_namespace(
        FakeEngine(connection),
        slug="team-a",
        actor_user_id="platform-admin",
        platform_roles=["SUPER_ADMIN"],
    )

    assert deleted == {"message": "Namespace deleted successfully"}
    assert "team-a" not in connection.namespaces


@pytest.mark.anyio
async def test_namespace_lifecycle_transitions_write_audit_logs() -> None:
    connection = FakeNamespaceMutationConnection(namespaces={
        "team-a": namespace_row(id=10, slug="team-a", status="ACTIVE"),
        "team-frozen": namespace_row(id=11, slug="team-frozen", status="FROZEN"),
        "team-archived": namespace_row(id=12, slug="team-archived", status="ARCHIVED"),
    }, members={
        10: {"admin": "ADMIN", "owner": "OWNER", "member": "MEMBER"},
        11: {"admin": "ADMIN", "owner": "OWNER"},
        12: {"owner": "OWNER"},
    })

    frozen = await freeze_namespace(
        FakeEngine(connection),
        slug="team-a",
        actor_user_id="admin",
        reason="maintenance",
        request_id="req-freeze",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )
    assert frozen["status"] == "FROZEN"
    assert connection.audit_rows[-1]["action"] == "FREEZE_NAMESPACE"
    assert connection.audit_rows[-1]["detail_json"] == '{"reason":"maintenance"}'

    unfrozen = await unfreeze_namespace(
        FakeEngine(connection),
        slug="team-frozen",
        actor_user_id="admin",
        request_id="req-unfreeze",
        client_ip=None,
        user_agent=None,
    )
    assert unfrozen["status"] == "ACTIVE"
    assert connection.audit_rows[-1]["action"] == "UNFREEZE_NAMESPACE"

    archived = await archive_namespace(
        FakeEngine(connection),
        slug="team-a",
        actor_user_id="owner",
        reason=None,
        request_id="req-archive",
        client_ip=None,
        user_agent=None,
    )
    assert archived["status"] == "ARCHIVED"
    assert connection.audit_rows[-1]["action"] == "ARCHIVE_NAMESPACE"

    restored = await restore_namespace(
        FakeEngine(connection),
        slug="team-archived",
        actor_user_id="owner",
        request_id="req-restore",
        client_ip=None,
        user_agent=None,
    )
    assert restored["status"] == "ACTIVE"
    assert connection.audit_rows[-1]["action"] == "RESTORE_NAMESPACE"


@pytest.mark.anyio
async def test_ordinary_profile_delete_and_lifecycle_lock_namespace_first() -> None:
    update_connection = FakeNamespaceMutationConnection()
    await update_namespace(
        FakeEngine(update_connection),
        slug="team-a",
        display_name="Updated",
        description=None,
        actor_user_id="admin",
    )
    assert "FOR UPDATE" in update_connection.statements[0]

    delete_connection = FakeNamespaceMutationConnection()
    await delete_namespace(
        FakeEngine(delete_connection), slug="team-a", actor_user_id="owner"
    )
    assert "FOR UPDATE" in delete_connection.statements[0]

    lifecycle_connection = FakeNamespaceMutationConnection()
    await freeze_namespace(
        FakeEngine(lifecycle_connection),
        slug="team-a",
        actor_user_id="admin",
        reason=None,
        request_id="lock-order",
        client_ip=None,
        user_agent=None,
    )
    assert "FOR UPDATE" in lifecycle_connection.statements[0]


def test_namespace_profile_lifecycle_routes_use_java_envelopes() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SKILL_ADMIN"])
    app.state.namespace_create_writer = lambda payload, user: {"slug": payload["slug"], "id": 50}
    app.state.namespace_update_writer = lambda slug, payload, user: {"slug": slug, "displayName": payload["displayName"]}
    app.state.namespace_delete_writer = lambda slug, user: {"message": "Namespace deleted successfully"}
    app.state.namespace_lifecycle_writer = lambda action, slug, payload, user, request: {"slug": slug, "status": action.upper()}
    client = TestClient(app)

    created = client.post(
        "/api/v1/namespaces",
        json={"slug": "team-b", "displayName": "Team B", "description": "new"},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert created.status_code == 200
    assert created.json()["msg"] == "创建成功"
    assert created.json()["data"] == {"slug": "team-b", "id": 50}

    updated = client.put(
        "/api/web/namespaces/team-b",
        json={"displayName": "Team B Updated", "description": "updated"},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert updated.status_code == 200
    assert updated.json()["msg"] == "更新成功"
    assert updated.json()["data"]["displayName"] == "Team B Updated"

    frozen = client.post(
        "/api/v1/namespaces/team-b/freeze",
        json={"reason": "maintenance"},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert frozen.status_code == 200
    assert frozen.json()["data"]["status"] == "FREEZE"

    deleted = client.delete("/api/web/namespaces/team-b", headers={"X-Mock-User-Id": "admin"})
    assert deleted.status_code == 200
    assert deleted.json()["msg"] == "删除成功"
    assert deleted.json()["data"]["message"] == "Namespace deleted successfully"
