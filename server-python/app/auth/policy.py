from __future__ import annotations

from typing import Any

from fastapi import HTTPException

NAMESPACE_OWNER_ROLE = "OWNER"
NAMESPACE_MANAGER_ROLES = {"OWNER", "ADMIN"}
NAMESPACE_MEMBER_ROLES = {"OWNER", "ADMIN", "MEMBER"}


def is_api_token_principal(user: dict[str, Any]) -> bool:
    return user.get("oauthProvider") == "api_token"


def namespace_role(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized else None


def namespace_role_allows(value: object | None, allowed_roles: set[str]) -> bool:
    normalized = namespace_role(value)
    return normalized in allowed_roles if normalized is not None else False


def is_namespace_owner(value: object | None) -> bool:
    return namespace_role(value) == NAMESPACE_OWNER_ROLE


def is_namespace_manager(value: object | None) -> bool:
    return namespace_role_allows(value, NAMESPACE_MANAGER_ROLES)


def is_namespace_member(value: object | None) -> bool:
    return namespace_role_allows(value, NAMESPACE_MEMBER_ROLES)


def managed_namespace_ids(namespace_roles: list[dict[str, Any]], allowed_roles: set[str] = NAMESPACE_MANAGER_ROLES) -> list[int]:
    return sorted(
        int(row["namespace_id"])
        for row in namespace_roles
        if namespace_role_allows(row.get("role"), allowed_roles)
    )


def platform_roles(user: dict[str, Any]) -> list[str]:
    return sorted({str(role) for role in user.get("platformRoles") or [] if str(role)})


def require_platform_role(user: dict[str, Any], role: str, *, detail: str) -> None:
    if role not in set(platform_roles(user)):
        raise HTTPException(status_code=403, detail=detail)


def require_any_platform_role(user: dict[str, Any], roles: set[str], *, detail: str) -> None:
    if set(platform_roles(user)).isdisjoint(roles):
        raise HTTPException(status_code=403, detail=detail)


def require_api_token_scope(user: dict[str, Any], scope: str) -> None:
    if not is_api_token_principal(user):
        return
    if scope not in {str(value) for value in user.get("tokenScopes") or []}:
        raise HTTPException(status_code=403, detail=f"Missing API token scope: {scope}")


def reject_api_token_principal_for_route(user: dict[str, Any], path: str) -> None:
    if is_api_token_principal(user):
        raise HTTPException(status_code=403, detail=f"API token cannot access endpoint: {path}")
