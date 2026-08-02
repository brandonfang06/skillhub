from fastapi.testclient import TestClient
import pytest

from app.api.auth import build_auth_methods, build_auth_providers, sanitize_return_to
from app.main import create_app


OAUTH_REGISTRATIONS = [
    {"id": "gitlab", "clientName": "GitLab", "clientId": "gitlab-client"},
    {"id": "github", "clientName": "GitHub", "clientId": "github-client"},
    {"id": "empty-name", "clientName": "", "clientId": "unnamed-client"},
]


def test_sanitize_return_to_matches_java_relative_path_rules() -> None:
    assert sanitize_return_to(None) is None
    assert sanitize_return_to("   ") is None
    assert sanitize_return_to("/dashboard/publish") == "/dashboard/publish"
    assert sanitize_return_to(" /settings/accounts ") == "/settings/accounts"
    assert sanitize_return_to("//evil.example") is None
    assert sanitize_return_to("https://evil.example") is None
    assert sanitize_return_to("/safe\r\nX-Bad: 1") is None


def test_build_auth_providers_sorts_oauth_and_encodes_safe_return_to() -> None:
    providers = build_auth_providers(OAUTH_REGISTRATIONS, return_to="/dashboard/publish?tab=one two")

    assert providers == [
        {
            "id": "empty-name",
            "name": "empty-name",
            "authorizationUrl": "/oauth2/authorization/empty-name?returnTo=%2Fdashboard%2Fpublish%3Ftab%3Done+two",
        },
        {
            "id": "github",
            "name": "GitHub",
            "authorizationUrl": "/oauth2/authorization/github?returnTo=%2Fdashboard%2Fpublish%3Ftab%3Done+two",
        },
        {
            "id": "gitlab",
            "name": "GitLab",
            "authorizationUrl": "/oauth2/authorization/gitlab?returnTo=%2Fdashboard%2Fpublish%3Ftab%3Done+two",
        },
    ]


def test_build_auth_providers_ignores_unsafe_return_to() -> None:
    providers = build_auth_providers(
        [{"id": "github", "clientName": "GitHub", "clientId": "github-client"}],
        return_to="https://evil.example",
    )

    assert providers == [{"id": "github", "name": "GitHub", "authorizationUrl": "/oauth2/authorization/github"}]


def test_build_auth_methods_matches_java_order_and_default_flags() -> None:
    methods = build_auth_methods(OAUTH_REGISTRATIONS, return_to="/dashboard", direct_enabled=False, session_bootstrap_enabled=False)

    assert methods == [
        {
            "id": "local-password",
            "methodType": "PASSWORD",
            "provider": "local",
            "displayName": "Local Account",
            "actionUrl": "/api/v1/auth/local/login",
        },
        {
            "id": "oauth-empty-name",
            "methodType": "OAUTH_REDIRECT",
            "provider": "empty-name",
            "displayName": "empty-name",
            "actionUrl": "/oauth2/authorization/empty-name?returnTo=%2Fdashboard",
        },
        {
            "id": "oauth-github",
            "methodType": "OAUTH_REDIRECT",
            "provider": "github",
            "displayName": "GitHub",
            "actionUrl": "/oauth2/authorization/github?returnTo=%2Fdashboard",
        },
        {
            "id": "oauth-gitlab",
            "methodType": "OAUTH_REDIRECT",
            "provider": "gitlab",
            "displayName": "GitLab",
            "actionUrl": "/oauth2/authorization/gitlab?returnTo=%2Fdashboard",
        },
    ]


@pytest.mark.parametrize(
    "client_id",
    [None, "", "   ", "placeholder", "CLIENT_PLACEHOLDER_VALUE", "replace-with-client-id"],
)
def test_auth_catalog_hides_unusable_oauth_client_ids(client_id: str | None) -> None:
    registrations = [
        {
            "id": "invalid",
            "clientName": "Invalid",
            "clientId": client_id,
        },
        {
            "id": "valid",
            "clientName": "Valid",
            "clientId": "client-123",
        },
    ]

    providers = build_auth_providers(registrations)
    methods = build_auth_methods(registrations)

    assert [provider["id"] for provider in providers] == ["valid"]
    assert [method["id"] for method in methods] == ["local-password", "oauth-valid"]


def test_build_auth_methods_includes_direct_local_only_when_enabled() -> None:
    methods = build_auth_methods([], return_to=None, direct_enabled=True, session_bootstrap_enabled=False)

    assert methods == [
        {
            "id": "local-password",
            "methodType": "PASSWORD",
            "provider": "local",
            "displayName": "Local Account",
            "actionUrl": "/api/v1/auth/local/login",
        },
        {
            "id": "direct-local",
            "methodType": "DIRECT_PASSWORD",
            "provider": "local",
            "displayName": "Local Account",
            "actionUrl": "/api/v1/auth/direct/login",
        },
    ]


def test_auth_catalog_routes_return_java_envelopes() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [
        {"id": "github", "clientName": "GitHub", "clientId": "github-client"}
    ]
    app.state.auth_direct_enabled = False
    app.state.auth_session_bootstrap_enabled = False
    client = TestClient(app)

    providers = client.get("/api/v1/auth/providers?returnTo=/dashboard")
    assert providers.status_code == 200
    assert providers.json()["code"] == 0
    assert providers.json()["data"] == [
        {"id": "github", "name": "GitHub", "authorizationUrl": "/oauth2/authorization/github?returnTo=%2Fdashboard"}
    ]

    methods = client.get("/api/v1/auth/methods?returnTo=https://evil.example")
    assert methods.status_code == 200
    assert methods.json()["code"] == 0
    assert methods.json()["data"][0]["id"] == "local-password"
    assert methods.json()["data"][1] == {
        "id": "oauth-github",
        "methodType": "OAUTH_REDIRECT",
        "provider": "github",
        "displayName": "GitHub",
        "actionUrl": "/oauth2/authorization/github",
    }
