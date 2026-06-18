from app.api import skills as api_skills
from app.skills import read_repository


def test_read_responses_module_owns_portal_response_helpers() -> None:
    from app.skills import read_responses

    for name in [
        "to_java_instant",
        "to_epoch_millis",
        "normalize_page_request",
        "paginate_rows",
        "build_versions_page_response",
        "build_version_detail_response",
        "build_tag_response",
        "to_lifecycle_version",
        "build_skill_detail_response",
        "build_skill_summary_response",
        "build_skill_search_response",
    ]:
        assert getattr(read_responses, name) is getattr(read_repository, name)
        assert getattr(read_responses, name) is getattr(api_skills, name)
