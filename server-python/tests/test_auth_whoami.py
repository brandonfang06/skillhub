from fastapi.testclient import TestClient

from app.api.auth import build_clawhub_whoami_response, build_cli_whoami_response
from app.main import create_app


def auth_user() -> dict[str, object]:
    return {
        "userId": "local-user",
        "displayName": "Local User",
        "email": "local-user@example.com",
        "avatarUrl": "https://example.test/avatar.png",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_build_clawhub_whoami_response_is_plain_json_contract() -> None:
    assert build_clawhub_whoami_response(auth_user()) == {
        "user": {
            "handle": "local-user",
            "displayName": "Local User",
            "image": "https://example.test/avatar.png",
        }
    }


def test_build_cli_whoami_response_matches_java_cli_shape() -> None:
    assert build_cli_whoami_response(auth_user()) == {
        "handle": "local-user",
        "displayName": "Local User",
        "email": "local-user@example.com",
    }


def test_whoami_routes_use_mock_user_bridge_and_java_contracts() -> None:
    app = create_app()
    seen_user_ids: list[str] = []

    def reader(user_id: str) -> dict[str, object] | None:
        seen_user_ids.append(user_id)
        return auth_user()

    app.state.auth_me_reader = reader
    client = TestClient(app)

    clawhub_response = client.get("/api/v1/whoami", headers={"X-Mock-User-Id": "local-user"})
    assert clawhub_response.status_code == 200
    assert "code" not in clawhub_response.json()
    assert clawhub_response.json() == {
        "user": {
            "handle": "local-user",
            "displayName": "Local User",
            "image": "https://example.test/avatar.png",
        }
    }

    cli_response = client.get("/api/cli/v1/auth/whoami", headers={"X-Mock-User-Id": "local-user"})
    assert cli_response.status_code == 200
    assert cli_response.json()["code"] == 0
    assert cli_response.json()["data"] == {
        "handle": "local-user",
        "displayName": "Local User",
        "email": "local-user@example.com",
    }
    assert seen_user_ids == ["local-user", "local-user"]


def test_whoami_routes_return_401_when_mock_user_missing_or_unknown() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: None
    client = TestClient(app)

    assert client.get("/api/v1/whoami").status_code == 401
    assert client.get("/api/cli/v1/auth/whoami").status_code == 401
    assert client.get("/api/v1/whoami", headers={"X-Mock-User-Id": "missing"}).status_code == 401
    assert client.get("/api/cli/v1/auth/whoami", headers={"X-Mock-User-Id": "missing"}).status_code == 401
