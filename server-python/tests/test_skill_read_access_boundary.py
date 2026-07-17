from app.api import skills as api_skills
from app.skills import read_repository
from app.skills.read_access import can_access_skill_row, can_manage_lifecycle_for_row


def test_read_access_module_owns_lifecycle_access_helpers() -> None:
    from app.skills import read_access

    for name in [
        "LIFECYCLE_MANAGER_STATUSES",
        "LIFECYCLE_LIST_PRIORITY",
        "lifecycle_visible_statuses",
        "lifecycle_list_priority",
        "can_manage_lifecycle_for_row",
        "can_access_skill_row",
        "assert_skill_row_access",
    ]:
        assert getattr(read_access, name) is getattr(read_repository, name)
        assert getattr(read_access, name) is getattr(api_skills, name)


def test_platform_read_override_does_not_grant_lifecycle_management() -> None:
    row = {
        "owner_id": "owner-a",
        "visibility": "PRIVATE",
        "latest_version_id": None,
    }

    assert can_access_skill_row(row, "platform-admin", None) is False
    assert can_access_skill_row(row, "platform-admin", None, platform_read_override=True) is True
    assert can_manage_lifecycle_for_row(row, "platform-admin", None) is False
