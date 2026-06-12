from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import create_app


def oauth_registration() -> dict[str, object]:
    return {
        "id": "github",
        "clientName": "GitHub",
        "clientId": "client-123",
        "authorizationUri": "https://github.example/oauth/authorize",
        "redirectUri": "http://localhost/login/oauth2/code/github",
        "scopes": ["read:user", "user:email"],
    }


def principal() -> dict[str, object]:
    return {
        "userId": "oauth-user",
        "displayName": "OAuth User",
        "email": "oauth-user@example.test",
        "avatarUrl": "",
        "oauthProvider": "github",
        "platformRoles": ["USER"],
    }


def test_oauth_authorization_redirects_when_provider_is_configured() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [oauth_registration()]
    client = TestClient(app)

    response = client.get("/oauth2/authorization/github?returnTo=/dashboard", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://github.example/oauth/authorize"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-123"]
    assert query["redirect_uri"] == ["http://localhost/login/oauth2/code/github"]
    assert query["scope"] == ["read:user user:email"]
    assert query["state"][0] != ""


def test_oauth_callback_rejects_missing_code() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [oauth_registration()]
    client = TestClient(app)

    response = client.get("/login/oauth2/code/github", follow_redirects=False)

    assert response.status_code == 400
    assert response.json()["detail"] == "error.auth.oauth.codeRequired"


def test_oauth_callback_rejects_unknown_provider() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [oauth_registration()]
    client = TestClient(app)

    response = client.get("/login/oauth2/code/gitlab?code=abc", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["detail"] == "error.auth.oauth.providerNotFound"


def test_oauth_callback_exchanges_code_binds_principal_and_creates_session() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [oauth_registration()]
    exchanged: list[tuple[str, str]] = []
    bound_claims: list[dict[str, object]] = []

    def exchanger(registration: dict[str, object], code: str) -> dict[str, object]:
        exchanged.append((str(registration["id"]), code))
        return {"subject": "12345", "providerLogin": "oauth-user", "email": "oauth-user@example.test"}

    def binder(registration: dict[str, object], claims: dict[str, object]) -> dict[str, object]:
        bound_claims.append(claims)
        return principal()

    app.state.oauth_code_exchanger = exchanger
    app.state.oauth_principal_binder = binder
    client = TestClient(app)

    redirect = client.get("/oauth2/authorization/github?returnTo=/dashboard", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    callback = client.get(f"/login/oauth2/code/github?code=abc&state={state}", follow_redirects=False)
    auth_me = client.get("/api/v1/auth/me")

    assert callback.status_code == 307
    assert callback.headers["location"] == "/dashboard"
    assert "SESSION" in client.cookies
    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == principal()
    assert exchanged == [("github", "abc")]
    assert bound_claims == [{"subject": "12345", "providerLogin": "oauth-user", "email": "oauth-user@example.test"}]
