from app.api import skills as api_skills
from app.skills import read_repository


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
