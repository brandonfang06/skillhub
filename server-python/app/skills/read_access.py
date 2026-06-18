from __future__ import annotations

from typing import Any

from app.auth.policy import is_namespace_manager, is_namespace_member
from app.skills.read_files import SkillResolveError


LIFECYCLE_MANAGER_STATUSES = (
    "PUBLISHED",
    "REJECTED",
    "PENDING_REVIEW",
    "UPLOADED",
    "DRAFT",
    "SCANNING",
    "SCAN_FAILED",
    "YANKED",
)
LIFECYCLE_LIST_PRIORITY = {status: index for index, status in enumerate(LIFECYCLE_MANAGER_STATUSES)}


def lifecycle_visible_statuses(can_manage: bool) -> tuple[str, ...]:
    return LIFECYCLE_MANAGER_STATUSES if can_manage else ("PUBLISHED",)


def lifecycle_list_priority(status: str) -> int:
    return LIFECYCLE_LIST_PRIORITY.get(status, len(LIFECYCLE_LIST_PRIORITY))


def can_manage_lifecycle_for_row(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> bool:
    return current_user_id is not None and (
        str(row["owner_id"]) == str(current_user_id) or is_namespace_manager(namespace_role)
    )


def can_access_skill_row(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> bool:
    visibility = str(row["visibility"])
    if row.get("latest_version_id") is None:
        return current_user_id is not None and str(row["owner_id"]) == str(current_user_id)
    if visibility == "PUBLIC":
        return True
    if visibility == "NAMESPACE_ONLY":
        return current_user_id is not None and is_namespace_member(namespace_role)
    if visibility == "PRIVATE":
        return can_manage_lifecycle_for_row(row, current_user_id, namespace_role)
    return False


def assert_skill_row_access(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> None:
    if not can_access_skill_row(row, current_user_id, namespace_role):
        raise SkillResolveError("error.skill.access.denied", status_code=403)


__all__ = [
    "LIFECYCLE_LIST_PRIORITY",
    "LIFECYCLE_MANAGER_STATUSES",
    "assert_skill_row_access",
    "can_access_skill_row",
    "can_manage_lifecycle_for_row",
    "lifecycle_list_priority",
    "lifecycle_visible_statuses",
]
