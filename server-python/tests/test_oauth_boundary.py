from fastapi.testclient import TestClient

from app.main import create_app


def test_oauth_authorization_boundary_returns_deferred_for_known_provider() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [{"id": "github", "clientName": "GitHub"}]
    client = TestClient(app)

    response = client.get("/oauth2/authorization/github?returnTo=/dashboard")

    assert response.status_code == 501
    assert response.json()["detail"] == "error.auth.oauth.deferred"


def test_oauth_authorization_boundary_rejects_unknown_provider() -> None:
    app = create_app()
    app.state.auth_oauth_registrations = [{"id": "github", "clientName": "GitHub"}]
    client = TestClient(app)

    response = client.get("/oauth2/authorization/unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "error.auth.oauth.providerNotFound"
