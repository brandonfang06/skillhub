from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _token_user(scopes: list[str]) -> dict[str, object]:
    return {
        "userId": "sync-user",
        "displayName": "Sync user",
        "email": "sync@example.test",
        "avatarUrl": "",
        "oauthProvider": "api_token",
        "platformRoles": ["USER"],
        "tokenScopes": scopes,
    }


def test_cli_namespace_manifest_returns_bearer_authorized_page() -> None:
    app = create_app()
    seen: list[dict[str, object]] = []
    app.state.auth_bearer_reader = lambda token: (
        _token_user(["skill:read"]) if token == "sk_sync" else None
    )
    app.state.cli_namespace_manifest_reader = lambda **kwargs: seen.append(kwargs) or {
        "items": [
            {
                "namespace": "team-a",
                "slug": "demo",
                "version": "1.0.0",
                "versionId": 42,
                "fingerprint": "sha256:fingerprint",
                "updatedAt": "2026-09-01T01:02:03Z",
                "visibility": "NAMESPACE_ONLY",
                "downloadUrl": "/api/v1/skills/team-a/demo/versions/1.0.0/download",
            }
        ],
        "nextCursor": "2",
    }
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/namespaces/team-a/skills?cursor=1&limit=25",
        headers={
            "Authorization": "Bearer sk_sync",
            "X-Request-Id": "namespace-manifest",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "namespace-manifest"
    assert response.json() == {
        "code": 0,
        "msg": "\u83b7\u53d6\u6210\u529f",
        "data": {
            "items": [
                {
                    "namespace": "team-a",
                    "slug": "demo",
                    "version": "1.0.0",
                    "versionId": 42,
                    "fingerprint": "sha256:fingerprint",
                    "updatedAt": "2026-09-01T01:02:03Z",
                    "visibility": "NAMESPACE_ONLY",
                    "downloadUrl": "/api/v1/skills/team-a/demo/versions/1.0.0/download",
                }
            ],
            "nextCursor": "2",
        },
        "timestamp": response.json()["timestamp"],
        "requestId": "namespace-manifest",
    }
    assert seen == [
        {
            "namespace": "team-a",
            "page": 1,
            "size": 25,
            "current_user_id": "sync-user",
        }
    ]


def test_cli_namespace_manifest_rejects_anonymous_and_wrong_scope() -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda token: _token_user(["skill:publish"])
    app.state.cli_namespace_manifest_reader = lambda **kwargs: pytest.fail(
        "unauthorized callers must not reach the manifest reader"
    )
    client = TestClient(app)

    anonymous = client.get("/api/cli/v1/namespaces/team-a/skills")
    wrong_scope = client.get(
        "/api/cli/v1/namespaces/team-a/skills",
        headers={
            "Authorization": "Bearer wrong-scope",
            "X-Request-Id": "manifest-wrong-scope",
        },
    )

    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "error.auth.required"
    assert wrong_scope.status_code == 403
    assert wrong_scope.headers["X-Request-Id"] == "manifest-wrong-scope"
    assert wrong_scope.json()["msg"] == "error.apiToken.scope.missing"
    assert wrong_scope.json()["data"] == {"args": ["skill:read"]}


def test_cli_namespace_manifest_accepts_session_identity_and_proxy_root_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    seen: list[dict[str, object]] = []

    async def session_principal(request: object) -> dict[str, object]:
        return {
            "userId": "session-user",
            "oauthProvider": "local",
            "platformRoles": ["USER"],
        }

    monkeypatch.setattr("app.auth.context.read_session_principal", session_principal)
    app.state.cli_namespace_manifest_reader = lambda **kwargs: seen.append(kwargs) or {
        "items": [],
        "nextCursor": None,
    }
    client = TestClient(app, root_path="/skillhub")

    response = client.get("/api/cli/v1/namespaces/team-a/skills")

    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "nextCursor": None}
    assert seen == [
        {
            "namespace": "team-a",
            "page": 0,
            "size": 100,
            "current_user_id": "session-user",
        }
    ]


@pytest.mark.parametrize("cursor", ["-1", "not-a-page"])
def test_cli_namespace_manifest_rejects_invalid_cursor(cursor: str) -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda token: _token_user(["skill:read"])
    app.state.cli_namespace_manifest_reader = lambda **kwargs: pytest.fail(
        "invalid cursor must not reach the manifest reader"
    )
    client = TestClient(app)

    response = client.get(
        f"/api/cli/v1/namespaces/team-a/skills?cursor={cursor}",
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "cursor must be a non-negative page number"
