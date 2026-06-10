from fastapi.testclient import TestClient

from app.main import create_app


def test_direct_login_is_disabled_by_default_with_java_error_key() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/direct/login",
        json={"provider": "local", "username": "alice", "password": "bad-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "error.auth.direct.disabled"


def test_session_bootstrap_is_disabled_by_default_with_java_error_key() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/api/v1/auth/session/bootstrap", json={"provider": "mock"})

    assert response.status_code == 403
    assert response.json()["detail"] == "error.auth.sessionBootstrap.disabled"


def test_enabled_direct_login_rejects_unsupported_provider_after_enabled_guard() -> None:
    app = create_app()
    app.state.auth_direct_enabled = True
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/direct/login",
        json={"provider": "saml", "username": "alice", "password": "bad-password"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.auth.direct.providerUnsupported"


def test_enabled_session_bootstrap_rejects_unsupported_provider_after_enabled_guard() -> None:
    app = create_app()
    app.state.auth_session_bootstrap_enabled = True
    client = TestClient(app)

    response = client.post("/api/v1/auth/session/bootstrap", json={"provider": "saml"})

    assert response.status_code == 400
    assert response.json()["detail"] == "error.auth.sessionBootstrap.providerUnsupported"


def test_enabled_direct_local_login_delegates_to_migrated_local_auth_response() -> None:
    app = create_app()
    app.state.auth_direct_enabled = True
    app.state.local_auth_login = lambda payload: {
        "userId": "user-1",
        "displayName": payload["username"],
        "email": "alice@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/direct/login",
        json={"provider": "local", "username": "alice", "password": "Abcd123!"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "response.success.read"
    assert response.json()["data"]["userId"] == "user-1"
