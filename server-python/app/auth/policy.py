from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def is_api_token_principal(user: dict[str, Any]) -> bool:
    return user.get("oauthProvider") == "api_token"


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
