from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.service_accounts.contracts import (
    ServicePrincipal,
    ServiceTokenMetadata,
    ServiceTokenSecret,
)


def admin_app() -> object:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SUPER_ADMIN"] if user_id == "admin" else ["USER"],
    }
    app.state.auth_bearer_reader = lambda _token: None
    now = datetime.now(UTC)
    principal = ServicePrincipal(
        "svc_1", "gitlab-importer", "GitLab Importer", "ACTIVE", "admin", now, now
    )
    token = ServiceTokenMetadata(
        1,
        "svc_1",
        "pipeline",
        "st_secretpr",
        ("source:import",),
        "admin",
        now,
        now + timedelta(days=30),
        None,
        None,
    )
    secret = ServiceTokenSecret(**token.__dict__, token="st_secret")
    app.state.service_principal_admin = {
        "list": lambda **_kwargs: ([principal], 1),
        "create": lambda **_kwargs: principal,
        "update": lambda **_kwargs: principal,
        "list_tokens": lambda **_kwargs: [token],
        "create_token": lambda **_kwargs: secret,
        "rotate_token": lambda **_kwargs: secret,
        "revoke_token": lambda **_kwargs: None,
    }
    return app


def test_service_principal_admin_requires_super_admin_session() -> None:
    client = TestClient(admin_app())
    assert client.get("/api/v1/admin/service-principals").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/service-principals", headers={"X-Mock-User-Id": "user"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/admin/service-principals",
            headers={"Authorization": "Bearer sk_personal"},
        ).status_code
        == 401
    )


def test_service_principal_admin_crud_returns_typed_envelopes_and_one_time_secret() -> (
    None
):
    client = TestClient(admin_app())
    headers = {"X-Mock-User-Id": "admin"}

    listing = client.get("/api/v1/admin/service-principals", headers=headers)
    created = client.post(
        "/api/v1/admin/service-principals",
        headers=headers,
        json={"code": "gitlab-importer", "displayName": "GitLab Importer"},
    )
    updated = client.patch(
        "/api/v1/admin/service-principals/svc_1",
        headers=headers,
        json={"displayName": "GitLab Importer", "status": "DISABLED"},
    )
    tokens = client.get(
        "/api/v1/admin/service-principals/svc_1/tokens", headers=headers
    )
    token_created = client.post(
        "/api/v1/admin/service-principals/svc_1/tokens",
        headers=headers,
        json={
            "name": "pipeline",
            "scopes": ["source:import"],
            "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    rotated = client.post(
        "/api/v1/admin/service-principals/svc_1/tokens/1/rotate",
        headers=headers,
        json={"expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
    )
    revoked = client.delete(
        "/api/v1/admin/service-principals/svc_1/tokens/1", headers=headers
    )

    assert listing.status_code == 200
    assert listing.json()["data"]["items"][0]["code"] == "gitlab-importer"
    assert created.status_code == 200
    assert updated.status_code == 200
    assert tokens.status_code == 200
    assert "token" not in tokens.json()["data"]["items"][0]
    assert token_created.json()["data"]["token"] == "st_secret"
    assert rotated.json()["data"]["token"] == "st_secret"
    assert revoked.status_code == 204
    assert listing.json()["requestId"]
