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


def test_authenticated_route_modules_do_not_import_auth_api_principal_helpers() -> None:
    api_dir = ROOT / "server-python" / "app" / "api"
    allowed = {api_dir / "auth.py"}
    offenders: list[str] = []
    for path in sorted(api_dir.glob("*.py")):
        if path in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        if "from app.api.auth import read_current_mock_user" in source:
            offenders.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    assert offenders == []


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


def test_platform_role_helpers_normalize_roles_and_preserve_route_error_details() -> None:
    from app.auth.policy import platform_roles, require_any_platform_role, require_platform_role

    user = {"platformRoles": ["", "USER", "SUPER_ADMIN", "USER"]}

    assert platform_roles(user) == ["SUPER_ADMIN", "USER"]
    require_platform_role(user, "SUPER_ADMIN", detail="error.admin.superAdminRequired")
    require_any_platform_role(user, {"SKILL_ADMIN", "SUPER_ADMIN"}, detail="error.admin.skillAdminRequired")

    with pytest.raises(HTTPException) as single_role_exc:
        require_platform_role(user, "AUDITOR", detail="error.admin.auditRequired")

    assert single_role_exc.value.status_code == 403
    assert single_role_exc.value.detail == "error.admin.auditRequired"

    with pytest.raises(HTTPException) as any_role_exc:
        require_any_platform_role(user, {"SKILL_ADMIN", "AUDITOR"}, detail="error.admin.skillAdminRequired")

    assert any_role_exc.value.status_code == 403
    assert any_role_exc.value.detail == "error.admin.skillAdminRequired"


def test_namespace_role_helpers_normalize_roles_and_select_managed_namespaces() -> None:
    from app.auth.policy import (
        NAMESPACE_MANAGER_ROLES,
        is_namespace_manager,
        is_namespace_member,
        is_namespace_owner,
        managed_namespace_ids,
        namespace_role,
        namespace_role_allows,
    )

    assert namespace_role(" owner ") == "OWNER"
    assert namespace_role("") is None
    assert namespace_role(None) is None
    assert is_namespace_owner("OWNER")
    assert is_namespace_manager("ADMIN")
    assert is_namespace_manager("OWNER")
    assert not is_namespace_manager("MEMBER")
    assert is_namespace_member("MEMBER")
    assert namespace_role_allows("admin", NAMESPACE_MANAGER_ROLES)
    assert managed_namespace_ids(
        [
            {"namespace_id": 3, "role": "MEMBER"},
            {"namespace_id": "1", "role": "OWNER"},
            {"namespace_id": 2, "role": "ADMIN"},
            {"namespace_id": 99, "role": ""},
        ]
    ) == [1, 2]


def test_namespace_policy_modules_use_shared_role_helpers() -> None:
    forbidden_fragments = [
        'NAMESPACE_GOVERNANCE_ROLES = {"OWNER", "ADMIN"}',
        'NAMESPACE_REVIEW_ROLES = {"OWNER", "ADMIN"}',
        'NAMESPACE_PROMOTION_ROLES = {"OWNER", "ADMIN"}',
        'LIFECYCLE_NAMESPACE_ROLES = {"OWNER", "ADMIN"}',
        'role in {"OWNER", "ADMIN"}',
        'role not in {"OWNER", "ADMIN"}',
        "namespace_role in NAMESPACE_",
        "str(row[\"role\"]) in NAMESPACE_",
        "namespace_roles.get(namespace_id) in NAMESPACE_",
    ]
    policy_modules = [
        "server-python/app/api/labels.py",
        "server-python/app/api/skills.py",
        "server-python/app/governance/workbench.py",
        "server-python/app/lifecycle/skill.py",
        "server-python/app/namespace/members.py",
        "server-python/app/namespace/mutations.py",
        "server-python/app/namespace/read.py",
        "server-python/app/promotion/workflow.py",
        "server-python/app/review/approval.py",
        "server-python/app/review/query.py",
        "server-python/app/security_audit.py",
    ]

    offenders: list[str] = []
    for relative in policy_modules:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in source:
                offenders.append(f"{relative}: {fragment}")

    assert offenders == []
