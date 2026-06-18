from app.api import skills as api_skills
from app.skills import compat_repository
from app.skills import read_repository


def test_read_compat_module_owns_clawhub_and_cli_helpers() -> None:
    from app.skills import read_compat

    for name in [
        "to_clawhub_canonical_slug",
        "from_clawhub_canonical_slug",
        "build_clawhub_search_response",
        "build_cli_search_response",
        "build_clawhub_skills_list_response",
        "build_clawhub_resolve_response",
        "build_cli_resolve_response",
        "build_clawhub_skill_detail_response",
        "clawhub_resolve_selectors",
    ]:
        assert getattr(read_compat, name) is getattr(read_repository, name)
        assert getattr(read_compat, name) is getattr(api_skills, name)
        assert getattr(read_compat, name) is getattr(compat_repository, name)
