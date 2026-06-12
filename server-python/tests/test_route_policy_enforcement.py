from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]


def test_high_risk_routes_do_not_import_auth_api_private_principal_helper() -> None:
    for relative in [
        "server-python/app/api/admin_policy.py",
        "server-python/app/api/tokens.py",
        "server-python/app/api/publish.py",
        "server-python/app/api/lifecycle.py",
    ]:
        source = (ROOT / relative).read_text(encoding="utf-8")

        assert "from app.api.auth import _read_current_user_or_401" not in source


def test_api_token_scope_policy_allows_mock_and_session_principals() -> None:
    from app.auth.policy import require_api_token_scope

    mock_user = {"oauthProvider": "mock", "platformRoles": ["USER"]}
    session_user = {"oauthProvider": "local", "platformRoles": ["USER"]}

    require_api_token_scope(mock_user, "token:manage")
    require_api_token_scope(session_user, "token:manage")


def test_api_token_scope_policy_rejects_missing_scope_only_for_api_tokens() -> None:
    from app.auth.policy import require_api_token_scope

    api_token_user = {"oauthProvider": "api_token", "tokenScopes": ["skill:read"]}

    with pytest.raises(HTTPException) as exc:
        require_api_token_scope(api_token_user, "skill:publish")

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing API token scope: skill:publish"


def test_admin_policy_rejects_api_token_principal_but_not_mock_or_session() -> None:
    from app.auth.policy import reject_api_token_principal_for_route

    reject_api_token_principal_for_route({"oauthProvider": "mock"}, "/api/v1/admin/users")
    reject_api_token_principal_for_route({"oauthProvider": "local"}, "/api/v1/admin/users")

    with pytest.raises(HTTPException) as exc:
        reject_api_token_principal_for_route({"oauthProvider": "api_token"}, "/api/v1/admin/users")

    assert exc.value.status_code == 403
    assert exc.value.detail == "API token cannot access endpoint: /api/v1/admin/users"
