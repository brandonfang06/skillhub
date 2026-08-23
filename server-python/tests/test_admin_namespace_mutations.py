from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app


def _user(user_id: str, roles: list[str]) -> dict[str, Any]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles,
    }


def _member(user_id: str = "member") -> dict[str, Any]:
    return {
        "id": 2,
        "namespaceId": 10,
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "role": "MEMBER",
        "createdAt": "2026-08-23T00:00:00Z",
        "updatedAt": "2026-08-23T00:00:00Z",
    }


def _detail(status: str = "ACTIVE") -> dict[str, Any]:
    return {
        "id": 10,
        "slug": "team-a",
        "displayName": "Team A",
        "status": status,
        "description": None,
        "type": "TEAM",
        "avatarUrl": None,
        "createdBy": "owner",
        "createdAt": "2026-08-23T00:00:00Z",
        "updatedAt": "2026-08-23T00:00:00Z",
        "stats": {"memberCount": 2, "skillCount": 0},
        "permissions": {
            "currentUserRole": None,
            "platformOverride": True,
            "immutable": False,
            "canManageMembers": status == "ACTIVE",
            "canGovernNamespace": True,
            "canPublish": status == "ACTIVE",
            "canTransferOwnership": status == "ACTIVE",
            "canFreeze": status == "ACTIVE",
            "canUnfreeze": status == "FROZEN",
            "canArchive": status in {"ACTIVE", "FROZEN"},
            "canRestore": status == "ARCHIVED",
        },
    }


def _configured_app() -> object:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: _user(
        user_id, ["SUPER_ADMIN"] if user_id == "admin" else ["USER_ADMIN"]
    )
    app.state.auth_bearer_reader = lambda token: (
        {**_user("token-admin", ["SUPER_ADMIN"]), "oauthProvider": "api_token"}
        if token == "valid"
        else None
    )
    app.state.admin_namespace_mutation_writer = _Writer()
    return app


class _Writer:
    async def add_member(self, **kwargs: Any) -> dict[str, Any]:
        return _member(kwargs["member_user_id"])

    async def batch_add_members(self, **kwargs: Any) -> dict[str, Any]:
        members = kwargs["members"]
        return {
            "totalCount": len(members),
            "successCount": len(members),
            "failureCount": 0,
            "results": [
                {
                    "userId": item["userId"],
                    "role": item["role"],
                    "success": True,
                    "error": None,
                }
                for item in members
            ],
        }

    async def update_member_role(self, **kwargs: Any) -> dict[str, Any]:
        return {**_member(kwargs["member_user_id"]), "role": kwargs["role"]}

    async def remove_member(self, **kwargs: Any) -> dict[str, str]:
        return {"message": "Member removed successfully"}

    async def transfer_ownership(self, **kwargs: Any) -> dict[str, str]:
        return {"message": "Ownership transferred successfully"}

    async def transition(self, **kwargs: Any) -> dict[str, Any]:
        status = {
            "freeze": "FROZEN",
            "unfreeze": "ACTIVE",
            "archive": "ARCHIVED",
            "restore": "ACTIVE",
        }[kwargs["action"]]
        return _detail(status)


def test_admin_namespace_route_inventory_includes_exact_mutations_without_web_aliases() -> (
    None
):
    routes = {
        (method, route.path)
        for route in create_app().routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/api/v1/admin/namespaces")
    }

    assert routes == {
        ("GET", "/api/v1/admin/namespaces"),
        ("GET", "/api/v1/admin/namespaces/{slug}"),
        ("GET", "/api/v1/admin/namespaces/{slug}/members"),
        ("GET", "/api/v1/admin/namespaces/{slug}/member-candidates"),
        ("POST", "/api/v1/admin/namespaces/{slug}/members"),
        ("POST", "/api/v1/admin/namespaces/{slug}/members/batch"),
        ("PUT", "/api/v1/admin/namespaces/{slug}/members/{userId}/role"),
        ("DELETE", "/api/v1/admin/namespaces/{slug}/members/{userId}"),
        ("POST", "/api/v1/admin/namespaces/{slug}/transfer-ownership"),
        ("POST", "/api/v1/admin/namespaces/{slug}/freeze"),
        ("POST", "/api/v1/admin/namespaces/{slug}/unfreeze"),
        ("POST", "/api/v1/admin/namespaces/{slug}/archive"),
        ("POST", "/api/v1/admin/namespaces/{slug}/restore"),
    }
    assert not any("/api/web/admin/namespaces" in path for _, path in routes)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/v1/admin/namespaces/team-a/members",
            {"userId": "member", "role": "MEMBER"},
        ),
        (
            "post",
            "/api/v1/admin/namespaces/team-a/members/batch",
            {"members": [{"userId": "member", "role": "MEMBER"}]},
        ),
        (
            "put",
            "/api/v1/admin/namespaces/team-a/members/member/role",
            {"role": "ADMIN"},
        ),
        ("delete", "/api/v1/admin/namespaces/team-a/members/member", None),
        (
            "post",
            "/api/v1/admin/namespaces/team-a/transfer-ownership",
            {"newOwnerId": "member"},
        ),
        ("post", "/api/v1/admin/namespaces/team-a/freeze", {"reason": "risk review"}),
        ("post", "/api/v1/admin/namespaces/team-a/unfreeze", None),
        ("post", "/api/v1/admin/namespaces/team-a/archive", {"reason": "retired"}),
        ("post", "/api/v1/admin/namespaces/team-a/restore", None),
    ],
)
def test_admin_namespace_mutations_are_session_super_admin_only(
    method: str, path: str, payload: dict[str, Any] | None
) -> None:
    client = TestClient(_configured_app())

    def call(
        target: str,
        *,
        json: dict[str, Any] | None,
        headers: dict[str, str] | None = None,
    ) -> object:
        return client.request(method.upper(), target, json=json, headers=headers)

    assert call(path, json=payload).status_code == 401
    assert (
        call(path, json=payload, headers={"X-Mock-User-Id": "user-admin"}).status_code
        == 403
    )
    bearer = call(path, json=payload, headers={"Authorization": "Bearer valid"})
    assert bearer.status_code == 403
    assert bearer.json()["msg"] == "error.apiToken.endpoint.unsupported"
    invalid = call(path, json=payload, headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    allowed = call(
        path,
        json=payload,
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "admin-write"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["requestId"] == "admin-write"


def test_admin_namespace_mutation_openapi_is_typed_and_validates_payloads() -> None:
    app = _configured_app()
    client = TestClient(app)
    headers = {"X-Mock-User-Id": "admin"}

    assert (
        client.post(
            "/api/v1/admin/namespaces/team-a/members/batch",
            json={"members": []},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/admin/namespaces/team-a/members",
            json={"userId": "member", "role": "OWNER"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/admin/namespaces/team-a/members/member/role",
            json={"role": "OWNER"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/admin/namespaces/team-a/transfer-ownership",
            json={"newOwnerId": "   "},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/admin/namespaces/team-a/freeze",
            json={"reason": "x" * 513},
            headers=headers,
        ).status_code
        == 422
    )

    schema = app.openapi()
    paths = schema["paths"]
    assert paths["/api/v1/admin/namespaces/{slug}/members"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("AdminNamespaceMemberRequest")
    assert paths["/api/v1/admin/namespaces/{slug}/members/batch"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]["$ref"].endswith(
        "AdminNamespaceBatchMemberEnvelope"
    )
    assert paths["/api/v1/admin/namespaces/{slug}/freeze"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("AdminNamespaceDetailEnvelope")
