from __future__ import annotations

from typing import Any

from app.auth.policy import is_namespace_manager
from app.skills.read_access import can_access_skill_row


COLLECTION_PLATFORM_CURATOR_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}


class CollectionAccessError(PermissionError):
    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.status_code = status_code


def can_curate_collection(
    namespace_type: str,
    namespace_role: str | None,
    platform_roles: list[str],
) -> bool:
    normalized_platform_roles = {str(role).strip().upper() for role in platform_roles}
    if normalized_platform_roles & COLLECTION_PLATFORM_CURATOR_ROLES:
        return True
    if str(namespace_type).strip().upper() == "GLOBAL":
        return False
    return is_namespace_manager(namespace_role)


def require_collection_curator(
    *,
    namespace_type: str,
    namespace_status: str,
    namespace_role: str | None,
    platform_roles: list[str],
) -> None:
    if str(namespace_status).strip().upper() != "ACTIVE":
        raise CollectionAccessError(
            "error.collection.namespace.inactive",
            status_code=409,
        )
    if not can_curate_collection(namespace_type, namespace_role, platform_roles):
        raise CollectionAccessError(
            "error.collection.curator.required",
            status_code=403,
        )


def can_read_collection_member(
    skill_projection: dict[str, Any],
    *,
    current_user_id: str | None,
    namespace_role: str | None,
    platform_roles: list[str],
) -> bool:
    return can_access_skill_row(
        skill_projection,
        current_user_id,
        namespace_role,
        platform_read_override="SUPER_ADMIN" in {str(role).strip().upper() for role in platform_roles},
    )
