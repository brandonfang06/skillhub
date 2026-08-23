from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def mock_user(user_id: str = "admin", roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["SUPER_ADMIN", "SKILL_ADMIN", "USER_ADMIN", "AUDITOR"],
    }


def bearer_user() -> dict[str, object]:
    user = mock_user("token-admin")
    user["oauthProvider"] = "api_token"
    user["tokenScopes"] = ["skill:read", "skill:publish", "skill:delete", "token:manage"]
    return user


def configure_admin_stubs(app: object) -> None:
    app.state.auth_me_reader = lambda user_id: mock_user(user_id)
    app.state.auth_bearer_reader = lambda raw_token: bearer_user() if raw_token == "sk_valid" else None
    app.state.admin_user_reader = lambda payload, user: {"items": [], "total": 0, "page": 0, "size": 20}
    app.state.admin_skill_hide_writer = lambda payload: {"hidden": True}
    app.state.admin_audit_log_reader = lambda payload, user: {"items": [], "total": 0, "page": 0, "size": 20}
    app.state.admin_skill_report_reader = lambda payload, user: {"items": [], "total": 0, "page": 0, "size": 20}
    app.state.admin_profile_review_approver = lambda request_id, user, request_meta: {"id": request_id, "status": "APPROVED"}
    app.state.admin_namespace_list_reader = lambda **kwargs: {
        "items": [],
        "total": 0,
        "page": 0,
        "size": 20,
        "stats": {"total": 0, "active": 0, "frozen": 0, "archived": 0},
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/v1/admin/users", None),
        ("post", "/api/v1/admin/skills/10/hide", {"reason": "policy"}),
        ("get", "/api/v1/admin/audit-logs", None),
        ("get", "/api/v1/admin/skill-reports", None),
        ("post", "/api/v1/admin/profile-reviews/20/approve", None),
    ],
)
def test_admin_routes_reject_api_token_principals_as_unsupported(method: str, path: str, body: dict[str, object] | None) -> None:
    app = create_app()
    configure_admin_stubs(app)
    client = TestClient(app)

    request = getattr(client, method)
    response = (
        request(path, headers={"Authorization": "Bearer sk_valid"})
        if body is None
        else request(path, headers={"Authorization": "Bearer sk_valid"}, json=body)
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["msg"] == "error.apiToken.endpoint.unsupported"
    assert payload["data"]["args"] == [path]
    assert payload["requestId"] == response.headers["X-Request-Id"]


def test_admin_routes_keep_invalid_bearer_unauthorized_and_mock_user_precedence() -> None:
    app = create_app()
    configure_admin_stubs(app)
    client = TestClient(app)

    invalid = client.get("/api/v1/admin/users", headers={"Authorization": "Bearer sk_missing"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "error.auth.required"

    mock_precedence = client.get(
        "/api/v1/admin/users",
        headers={"X-Mock-User-Id": "admin", "Authorization": "Bearer sk_valid"},
    )
    assert mock_precedence.status_code == 200


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespaces",
        "/api/v1/admin/users",
    ],
)
def test_admin_bearer_policy_is_case_insensitive_for_valid_tokens(
    scheme: str,
    path: str,
) -> None:
    app = create_app()
    configure_admin_stubs(app)
    client = TestClient(app)

    response = client.get(
        path,
        headers={"Authorization": f"{scheme} sk_valid"},
    )

    assert response.status_code == 403
    assert response.json()["msg"] == "error.apiToken.endpoint.unsupported"
    assert response.json()["data"]["args"] == [path]


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespaces",
        "/api/v1/admin/users",
    ],
)
def test_admin_bearer_policy_keeps_invalid_tokens_unauthorized(
    scheme: str,
    path: str,
) -> None:
    app = create_app()
    configure_admin_stubs(app)
    client = TestClient(app)

    response = client.get(
        path,
        headers={"Authorization": f"{scheme} sk_missing"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
