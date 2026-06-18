from app.api import skills as api_skills
from app.skills import read_repository


def test_read_resolve_module_owns_resolve_helpers() -> None:
    from app.skills import read_resolve

    for name in [
        "has_text",
        "compute_version_fingerprint",
        "find_latest_version",
        "matched_value",
        "resolve_version_row",
        "build_resolve_response",
    ]:
        assert getattr(read_resolve, name) is getattr(read_repository, name)
        assert getattr(read_resolve, name) is getattr(api_skills, name)
