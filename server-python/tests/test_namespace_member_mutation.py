from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace.members import (
    NamespaceMemberReadError,
    add_namespace_member,
    batch_add_namespace_members,
    remove_namespace_member,
    transfer_namespace_ownership,
    update_namespace_member_role,
)
from tests.support.builders import auth_user, namespace_member_row as member_row, namespace_row, user_row
from tests.support.fake_db import FakeEngine, FakeResult


class FakeNamespaceMutationConnection:
    def __init__(
        self,
        *,
        namespace: dict[str, Any] | None = None,
        operator_role: str | None = "OWNER",
        members: dict[str, dict[str, Any]] | None = None,
        users: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.namespace = namespace or namespace_row()
        self.operator_role = operator_role
        self.members = members or {"operator": member_row(user_id="operator", role=operator_role or "MEMBER")}
        self.users = users or {
            "operator": user_row(id="operator", display_name="Operator"),
            "new-user": user_row(id="new-user", display_name="New User"),
            "member": user_row(id="member", display_name="Member User"),
        }
        self.next_member_id = 200
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "FROM namespace n" in sql:
            return FakeResult(row=self.namespace) if self.namespace else FakeResult()
        if "SELECT role" in sql and "FROM namespace_member" in sql:
            user_id = str(bound["user_id"])
            row = self.members.get(user_id)
            return FakeResult(row={"role": row["role"]}) if row else FakeResult()
        if "SELECT nm.id" in sql and "FROM namespace_member nm" in sql:
            row = self.members.get(str(bound["user_id"]))
            return FakeResult(row=self._member_response_row(row)) if row else FakeResult()
        if "INSERT INTO namespace_member" in sql:
            user_id = str(bound["user_id"])
            self.next_member_id += 1
            self.members[user_id] = member_row(
                id=self.next_member_id,
                namespace_id=int(bound["namespace_id"]),
                user_id=user_id,
                role=str(bound["role"]),
            )
            return FakeResult(row=self._member_response_row(self.members[user_id]))
        if "UPDATE namespace_member" in sql:
            user_id = str(bound["user_id"])
            self.members[user_id]["role"] = str(bound["role"])
            return FakeResult(row=self._member_response_row(self.members[user_id]))
        if "DELETE FROM namespace_member" in sql:
            self.members.pop(str(bound["user_id"]), None)
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")

    def _member_response_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        user = self.users.get(str(row["user_id"]))
        return {
            **row,
            "display_name": user["display_name"] if user else None,
            "email": user["email"] if user else None,
        }

@pytest.mark.anyio
async def test_add_namespace_member_matches_java_rules() -> None:
    connection = FakeNamespaceMutationConnection()

    response = await add_namespace_member(
        FakeEngine(connection),
        slug="team-a",
        member_user_id="new-user",
        role="ADMIN",
        operator_user_id="operator",
    )

    assert response["userId"] == "new-user"
    assert response["displayName"] == "New User"
    assert response["role"] == "ADMIN"

    with pytest.raises(NamespaceMemberReadError, match="error.namespace.member.alreadyExists"):
        await add_namespace_member(FakeEngine(connection), slug="team-a", member_user_id="new-user", role="MEMBER", operator_user_id="operator")

    with pytest.raises(NamespaceMemberReadError, match="error.namespace.member.owner.assignDirect"):
        await add_namespace_member(FakeEngine(connection), slug="team-a", member_user_id="owner-2", role="OWNER", operator_user_id="operator")


@pytest.mark.anyio
async def test_update_and_remove_namespace_member_match_java_rules() -> None:
    connection = FakeNamespaceMutationConnection(
        members={
            "operator": member_row(user_id="operator", role="OWNER"),
            "member": member_row(user_id="member", role="MEMBER"),
            "owner-member": member_row(user_id="owner-member", role="OWNER"),
        }
    )

    updated = await update_namespace_member_role(
        FakeEngine(connection),
        slug="team-a",
        member_user_id="member",
        role="ADMIN",
        operator_user_id="operator",
    )
    assert updated["role"] == "ADMIN"

    with pytest.raises(NamespaceMemberReadError, match="error.namespace.member.owner.setDirect"):
        await update_namespace_member_role(FakeEngine(connection), slug="team-a", member_user_id="member", role="OWNER", operator_user_id="operator")

    with pytest.raises(NamespaceMemberReadError, match="error.namespace.member.owner.remove"):
        await remove_namespace_member(FakeEngine(connection), slug="team-a", member_user_id="owner-member", operator_user_id="operator")

    removed = await remove_namespace_member(FakeEngine(connection), slug="team-a", member_user_id="member", operator_user_id="operator")
    assert removed == {"message": "Member removed successfully"}
    assert "member" not in connection.members


@pytest.mark.anyio
async def test_member_mutations_enforce_namespace_and_operator_boundaries() -> None:
    readonly = FakeNamespaceMutationConnection(namespace=namespace_row(status="FROZEN"))
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.readonly") as frozen:
        await add_namespace_member(FakeEngine(readonly), slug="team-a", member_user_id="new-user", role="MEMBER", operator_user_id="operator")
    assert frozen.value.status_code == 400

    global_ns = FakeNamespaceMutationConnection(namespace=namespace_row(type="GLOBAL", slug="global"))
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.system.immutable") as immutable:
        await add_namespace_member(FakeEngine(global_ns), slug="global", member_user_id="new-user", role="MEMBER", operator_user_id="operator")
    assert immutable.value.status_code == 400

    member_operator = FakeNamespaceMutationConnection(operator_role="MEMBER")
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.admin.required") as forbidden:
        await add_namespace_member(FakeEngine(member_operator), slug="team-a", member_user_id="new-user", role="MEMBER", operator_user_id="operator")
    assert forbidden.value.status_code == 403


@pytest.mark.anyio
async def test_transfer_namespace_ownership_matches_java_role_swap() -> None:
    connection = FakeNamespaceMutationConnection(
        members={
            "owner": member_row(user_id="owner", role="OWNER"),
            "new-owner": member_row(user_id="new-owner", role="ADMIN"),
        },
        users={
            "owner": user_row(id="owner", display_name="Owner"),
            "new-owner": user_row(id="new-owner", display_name="New Owner"),
        },
    )

    response = await transfer_namespace_ownership(
        FakeEngine(connection),
        slug="team-a",
        current_owner_id="owner",
        new_owner_id="new-owner",
    )

    assert response == {"message": "Ownership transferred successfully"}
    assert connection.members["owner"]["role"] == "ADMIN"
    assert connection.members["new-owner"]["role"] == "OWNER"


@pytest.mark.anyio
async def test_transfer_namespace_ownership_preserves_java_error_keys() -> None:
    missing_current = FakeNamespaceMutationConnection(
        members={"new-owner": member_row(user_id="new-owner", role="ADMIN")}
    )
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.owner.current.notFound") as current_missing:
        await transfer_namespace_ownership(
            FakeEngine(missing_current),
            slug="team-a",
            current_owner_id="missing-owner",
            new_owner_id="new-owner",
        )
    assert current_missing.value.status_code == 400

    invalid_current = FakeNamespaceMutationConnection(
        members={
            "member": member_row(user_id="member", role="MEMBER"),
            "new-owner": member_row(user_id="new-owner", role="ADMIN"),
        }
    )
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.owner.current.invalid") as current_invalid:
        await transfer_namespace_ownership(
            FakeEngine(invalid_current),
            slug="team-a",
            current_owner_id="member",
            new_owner_id="new-owner",
        )
    assert current_invalid.value.status_code == 400

    missing_new = FakeNamespaceMutationConnection(members={"owner": member_row(user_id="owner", role="OWNER")})
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.owner.new.notFound") as new_missing:
        await transfer_namespace_ownership(
            FakeEngine(missing_new),
            slug="team-a",
            current_owner_id="owner",
            new_owner_id="missing-new-owner",
        )
    assert new_missing.value.status_code == 400

    readonly = FakeNamespaceMutationConnection(namespace=namespace_row(status="FROZEN"))
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.readonly") as frozen:
        await transfer_namespace_ownership(
            FakeEngine(readonly),
            slug="team-a",
            current_owner_id="operator",
            new_owner_id="member",
        )
    assert frozen.value.status_code == 400

    global_ns = FakeNamespaceMutationConnection(namespace=namespace_row(type="GLOBAL", slug="global"))
    with pytest.raises(NamespaceMemberReadError, match="error.namespace.readonly") as immutable:
        await transfer_namespace_ownership(
            FakeEngine(global_ns),
            slug="global",
            current_owner_id="operator",
            new_owner_id="member",
        )
    assert immutable.value.status_code == 400


def test_transfer_ownership_route_returns_java_envelope_for_v1_and_web_aliases() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.namespace_transfer_ownership_writer = lambda slug, current_owner_id, new_owner_id: {
        "message": f"Ownership transferred successfully:{slug}:{current_owner_id}:{new_owner_id}"
    }
    client = TestClient(app)

    for prefix in ("/api/v1", "/api/web"):
        response = client.post(
            f"{prefix}/namespaces/team-a/transfer-ownership",
            json={"newOwnerId": "new-owner"},
            headers={"X-Mock-User-Id": "owner"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["msg"] == "更新成功"
        assert body["data"] == {"message": "Ownership transferred successfully:team-a:owner:new-owner"}
        assert body["requestId"]


def test_transfer_ownership_route_requires_authentication() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: None
    app.state.namespace_transfer_ownership_writer = lambda slug, current_owner_id, new_owner_id: {
        "message": "unexpected"
    }
    client = TestClient(app)

    response = client.post("/api/v1/namespaces/team-a/transfer-ownership", json={"newOwnerId": "new-owner"})

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


@pytest.mark.anyio
async def test_batch_add_namespace_members_preserves_partial_success() -> None:
    connection = FakeNamespaceMutationConnection(members={"operator": member_row(user_id="operator", role="OWNER")})

    response = await batch_add_namespace_members(
        FakeEngine(connection),
        slug="team-a",
        members=[
            {"userId": "new-user", "role": "MEMBER"},
            {"userId": "new-user", "role": "ADMIN"},
            {"userId": "direct-owner", "role": "OWNER"},
        ],
        operator_user_id="operator",
    )

    assert response["totalCount"] == 3
    assert response["successCount"] == 1
    assert response["failureCount"] == 2
    assert response["results"] == [
        {"userId": "new-user", "role": "MEMBER", "success": True, "error": None},
        {"userId": "new-user", "role": "ADMIN", "success": False, "error": "ALREADY_MEMBER"},
        {"userId": "direct-owner", "role": "OWNER", "success": False, "error": "INVALID_ROLE"},
    ]


def test_namespace_member_mutation_routes_use_java_envelopes_and_boundaries() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)
    app.state.namespace_member_add_writer = lambda slug, member_user_id, role, operator_user_id: {
        "id": 201,
        "namespaceId": 10,
        "userId": member_user_id,
        "displayName": "New User",
        "email": "new-user@example.test",
        "role": role,
        "createdAt": "2026-06-10T08:05:00Z",
        "updatedAt": "2026-06-10T08:05:00Z",
    }
    app.state.namespace_member_update_writer = lambda slug, member_user_id, role, operator_user_id: {
        "id": 201,
        "namespaceId": 10,
        "userId": member_user_id,
        "displayName": "Member User",
        "email": "member@example.test",
        "role": role,
        "createdAt": "2026-06-10T08:05:00Z",
        "updatedAt": "2026-06-10T09:05:00Z",
    }
    app.state.namespace_member_remove_writer = lambda slug, member_user_id, operator_user_id: {"message": "Member removed successfully"}
    app.state.namespace_member_batch_add_writer = lambda slug, members, operator_user_id: {
        "totalCount": len(members),
        "successCount": 1,
        "failureCount": 0,
        "results": [{"userId": members[0]["userId"], "role": members[0]["role"], "success": True, "error": None}],
    }
    client = TestClient(app)

    assert client.post("/api/v1/namespaces/team-a/members", json={"userId": "new-user", "role": "MEMBER"}).status_code == 401

    add_response = client.post(
        "/api/v1/namespaces/team-a/members",
        json={"userId": "new-user", "role": "ADMIN"},
        headers={"X-Mock-User-Id": "operator", "X-Request-Id": "member-add"},
    )
    assert add_response.status_code == 200
    assert add_response.json()["msg"] == "\u521b\u5efa\u6210\u529f"
    assert add_response.json()["requestId"] == "member-add"
    assert add_response.json()["data"]["role"] == "ADMIN"

    update_response = client.put(
        "/api/web/namespaces/team-a/members/new-user/role",
        json={"role": "MEMBER"},
        headers={"X-Mock-User-Id": "operator"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert update_response.json()["data"]["role"] == "MEMBER"

    batch_response = client.post(
        "/api/web/namespaces/team-a/members/batch",
        json={"members": [{"userId": "new-user", "role": "MEMBER"}]},
        headers={"X-Mock-User-Id": "operator"},
    )
    assert batch_response.status_code == 200
    assert batch_response.json()["data"]["totalCount"] == 1

    remove_response = client.delete("/api/v1/namespaces/team-a/members/new-user", headers={"X-Mock-User-Id": "operator"})
    assert remove_response.status_code == 200
    assert remove_response.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert remove_response.json()["data"]["message"] == "Member removed successfully"
