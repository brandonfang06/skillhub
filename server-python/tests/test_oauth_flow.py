from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.auth.oauth import _claims_from_attributes, oauth_registrations_from_env


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
        "canChangePassword": False,
        "platformRoles": ["USER"],
    }


class FakeMappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, object]]:
        return self.rows

    def one_or_none(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None, row: dict[str, object] | None = None) -> None:
        self.rows = rows if rows is not None else ([row] if row is not None else [])

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeTransaction:
    def __init__(self, connection: "FakeOAuthConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeOAuthConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeOAuthConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeOAuthConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}
        self.identity_bindings: list[dict[str, object]] = []
        self.namespace_members: list[dict[str, object]] = []

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM identity_binding ib" in sql:
            row = next(
                (
                    binding
                    for binding in self.identity_bindings
                    if binding["provider_code"] == bound["provider_code"] and binding["subject"] == bound["subject"]
                ),
                None,
            )
            if row is None:
                return FakeResult()
            user = self.users[str(row["user_id"])]
            return FakeResult(
                row={
                    "binding_id": row["id"],
                    "id": user["id"],
                    "display_name": user["display_name"],
                    "email": user["email"],
                    "avatar_url": user["avatar_url"],
                    "status": user["status"],
                }
            )
        if "INSERT INTO user_account" in sql:
            self.users[str(bound["id"])] = {
                "id": bound["id"],
                "display_name": bound["display_name"],
                "email": bound["email"],
                "avatar_url": bound["avatar_url"],
                "status": "ACTIVE",
            }
            return FakeResult()
        if "INSERT INTO identity_binding" in sql:
            self.identity_bindings.append(
                {
                    "id": len(self.identity_bindings) + 1,
                    "user_id": bound["user_id"],
                    "provider_code": bound["provider_code"],
                    "subject": bound["subject"],
                    "login_name": bound["login_name"],
                }
            )
            return FakeResult()
        if "FROM namespace" in sql and "slug = 'global'" in sql:
            return FakeResult(row={"id": 1, "slug": "global"})
        if "FROM namespace_member" in sql:
            row = next(
                (
                    member
                    for member in self.namespace_members
                    if member["namespace_id"] == bound["namespace_id"] and member["user_id"] == bound["user_id"]
                ),
                None,
            )
            return FakeResult(row=row) if row else FakeResult()
        if "INSERT INTO namespace_member" in sql:
            self.namespace_members.append(
                {"namespace_id": bound["namespace_id"], "user_id": bound["user_id"], "role": bound["role"]}
            )
            return FakeResult()
        if "FROM user_role_binding" in sql:
            return FakeResult()
        if "UPDATE user_account" in sql:
            user = self.users[str(bound["user_id"])]
            user["display_name"] = bound["display_name"]
            user["email"] = bound["email"]
            user["avatar_url"] = bound["avatar_url"]
            return FakeResult()
        if "UPDATE identity_binding" in sql:
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeOAuthHttpClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    async def __aenter__(self) -> "FakeOAuthHttpClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(self, url: str, data: dict[str, object], headers: dict[str, str]) -> FakeHttpResponse:
        self.requests.append(("POST", url, {"data": data, "headers": headers}))
        return FakeHttpResponse({"access_token": "oauth-access-token", "token_type": "bearer"})

    async def get(self, url: str, headers: dict[str, str]) -> FakeHttpResponse:
        self.requests.append(("GET", url, {"headers": headers}))
        return FakeHttpResponse(
            {
                "id": 12345,
                "login": "oauth-user",
                "email": "oauth-user@example.test",
                "avatar_url": "https://avatar.example/user.png",
            }
        )


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


def test_legacy_github_gitlab_env_is_not_advertised_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH2_GITHUB_CLIENT_ID", "env-client")
    monkeypatch.setenv("OAUTH2_GITHUB_CLIENT_SECRET", "env-secret")
    monkeypatch.setenv("OAUTH2_GITLAB_CLIENT_ID", "gitlab-client")
    monkeypatch.setenv("OAUTH2_GITLAB_CLIENT_SECRET", "gitlab-secret")

    registrations = {str(item["id"]) for item in oauth_registrations_from_env()}

    assert "github" not in registrations
    assert "gitlab" not in registrations


def test_keycloak_registration_uses_spring_boot_oidc_env_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub/")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID", "skillhub-web")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET", "keycloak-secret")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_PROVIDER", "keycloak")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_SCOPE", "openid,profile,email")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_NAME", "Keycloak")
    monkeypatch.setenv(
        "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_REDIRECT_URI",
        "{baseUrl}/login/oauth2/code/{registrationId}",
    )
    monkeypatch.setenv(
        "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI",
        "https://id.example.test/realms/skillhub",
    )

    registrations = {str(item["id"]): item for item in oauth_registrations_from_env()}

    keycloak = registrations["keycloak"]
    assert keycloak["clientName"] == "Keycloak"
    assert keycloak["clientId"] == "skillhub-web"
    assert keycloak["clientSecret"] == "keycloak-secret"
    assert keycloak["authorizationUri"] == "https://id.example.test/realms/skillhub/protocol/openid-connect/auth"
    assert keycloak["tokenUri"] == "https://id.example.test/realms/skillhub/protocol/openid-connect/token"
    assert keycloak["userInfoUri"] == "https://id.example.test/realms/skillhub/protocol/openid-connect/userinfo"
    assert keycloak["redirectUri"] == "https://skillhub.example/skillhub/login/oauth2/code/keycloak"
    assert keycloak["scopes"] == ["openid", "profile", "email"]


def test_keycloak_authorization_redirects_from_spring_boot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID", "skillhub-web")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET", "keycloak-secret")
    monkeypatch.setenv("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_SCOPE", "openid,profile,email")
    monkeypatch.setenv(
        "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI",
        "https://id.example.test/realms/skillhub",
    )
    app = create_app()
    client = TestClient(app)

    response = client.get("/oauth2/authorization/keycloak?returnTo=/dashboard", follow_redirects=False)

    assert response.status_code == 307
    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://id.example.test/realms/skillhub/protocol/openid-connect/auth"
    )
    assert query["client_id"] == ["skillhub-web"]
    assert query["redirect_uri"] == ["https://skillhub.example/login/oauth2/code/keycloak"]
    assert query["scope"] == ["openid profile email"]


def test_keycloak_claims_use_sub_and_preferred_username() -> None:
    claims = _claims_from_attributes(
        "keycloak",
        {
            "sub": "1e52e2cf-1f10-4b8b-9f41-71ad3e845791",
            "preferred_username": "alice",
            "name": "Alice Example",
            "email": "alice@example.test",
        },
    )

    assert claims["subject"] == "1e52e2cf-1f10-4b8b-9f41-71ad3e845791"
    assert claims["providerLogin"] == "alice"
    assert claims["email"] == "alice@example.test"


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


def test_oauth_callback_redirects_to_the_public_subpath(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skillhub.example/skillhub")
    app = create_app()
    app.state.auth_oauth_registrations = [oauth_registration()]
    app.state.oauth_code_exchanger = lambda registration, code: {
        "subject": "12345",
        "providerLogin": "oauth-user",
        "email": "oauth-user@example.test",
    }
    app.state.oauth_principal_binder = lambda registration, claims: principal()
    client = TestClient(app)

    authorization = client.get(
        "/oauth2/authorization/github?returnTo=/skills/example",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(authorization.headers["location"]).query)["state"][0]

    callback = client.get(f"/login/oauth2/code/github?code=abc&state={state}", follow_redirects=False)

    assert callback.status_code == 307
    assert callback.headers["location"] == "/skillhub/skills/example"


def test_oauth_callback_uses_default_exchange_and_identity_binding_when_no_test_doubles() -> None:
    connection = FakeOAuthConnection()
    http_client = FakeOAuthHttpClient()
    app = create_app()
    app.state.db_engine = FakeEngine(connection)
    app.state.auth_oauth_registrations = [
        {
            **oauth_registration(),
            "clientSecret": "secret-123",
            "tokenUri": "https://github.example/oauth/token",
            "userInfoUri": "https://github.example/user",
        }
    ]
    app.state.oauth_http_client_factory = lambda: http_client
    client = TestClient(app)

    redirect = client.get("/oauth2/authorization/github?returnTo=/dashboard", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    callback = client.get(f"/login/oauth2/code/github?code=abc&state={state}", follow_redirects=False)
    auth_me = client.get("/api/v1/auth/me")

    assert callback.status_code == 307
    assert auth_me.status_code == 200
    assert auth_me.json()["data"] == {
        "userId": next(iter(connection.users)),
        "displayName": "oauth-user",
        "email": "oauth-user@example.test",
        "avatarUrl": "https://avatar.example/user.png",
        "oauthProvider": "github",
        "canChangePassword": False,
        "platformRoles": ["USER"],
    }
    assert connection.identity_bindings[0]["provider_code"] == "github"
    assert connection.identity_bindings[0]["subject"] == "12345"
    assert connection.namespace_members == [
        {"namespace_id": 1, "user_id": next(iter(connection.users)), "role": "MEMBER"}
    ]
    assert http_client.requests[0][0:2] == ("POST", "https://github.example/oauth/token")
    assert http_client.requests[1][0:2] == ("GET", "https://github.example/user")
