from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


DEFAULT_NOW = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def user_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "user-1",
        "display_name": "User One",
        "email": "user-1@example.test",
        "avatar_url": "",
        "status": "ACTIVE",
        "created_at": DEFAULT_NOW,
        "updated_at": DEFAULT_NOW,
    }
    data.update(overrides)
    return data


def auth_user(user_id: str = "user-1", *, platform_roles: list[str] | None = None, oauth_provider: str = "mock") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": oauth_provider,
        "platformRoles": platform_roles or ["USER"],
    }


def bearer_user(user_id: str = "token-user", scopes: list[str] | None = None) -> dict[str, object]:
    data = auth_user(user_id, oauth_provider="api_token")
    data["tokenScopes"] = scopes if scopes is not None else ["token:manage"]
    return data


def namespace_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"id": 10, "slug": "team-a", "status": "ACTIVE", "type": "TEAM"}
    data.update(overrides)
    return data


def namespace_member_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 101,
        "namespace_id": 10,
        "user_id": "member",
        "role": "MEMBER",
        "created_at": DEFAULT_NOW,
        "updated_at": DEFAULT_NOW,
    }
    data.update(overrides)
    return data


def skill_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "skill_id": 10,
        "namespace_id": 1,
        "namespace_slug": "team",
        "skill_slug": "demo",
        "owner_id": "owner-1",
        "latest_version_id": 102,
    }
    data.update(overrides)
    return data


def skill_version_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"version_id": 101, "skill_id": 10, "version": "1.0.0", "status": "PUBLISHED"}
    data.update(overrides)
    return data


def review_task_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 301,
        "skill_version_id": 501,
        "namespace_id": 1,
        "status": "PENDING",
        "version": 1,
        "submitted_by": "submitter",
        "submitted_at": DEFAULT_NOW,
    }
    data.update(overrides)
    return data


def promotion_request_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 301,
        "source_skill_id": 101,
        "source_version_id": 501,
        "target_namespace_id": 1,
        "target_skill_id": None,
        "status": "PENDING",
        "version": 1,
        "submitted_by": "submitter",
        "submitted_at": DEFAULT_NOW,
    }
    data.update(overrides)
    return data


def token_row(
    token_id: int = 1,
    user_id: str = "user-1",
    name: str = "CLI",
    prefix: str = "sk_token",
    token_hash: str = "token-hash",
    scopes: list[str] | None = None,
    created_at: str | datetime = DEFAULT_NOW,
    *,
    revoked: bool = False,
) -> dict[str, Any]:
    parsed_created_at = (
        datetime.fromisoformat(created_at.replace("Z", "+00:00")) if isinstance(created_at, str) else created_at
    )
    return {
        "id": token_id,
        "subject_type": "USER",
        "subject_id": user_id,
        "user_id": user_id,
        "name": name,
        "token_prefix": prefix,
        "token_hash": token_hash,
        "scope_json": scopes or [],
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": datetime(2026, 6, 10, 12, 0, tzinfo=UTC) if revoked else None,
        "created_at": parsed_created_at,
    }
