from app.api import skills as api_skills
from app.skills import read_repository


def test_read_compare_module_owns_compare_helpers() -> None:
    from app.skills import read_compare

    for name in [
        "COMPARE_MAX_FILE_BYTES",
        "COMPARE_MAX_LINES",
        "BINARY_FILE_EXTENSIONS",
        "is_binary_compare_path",
        "split_compare_lines",
        "build_compare_hunks",
        "build_compare_file",
        "build_compare_response",
    ]:
        assert getattr(read_compare, name) is getattr(read_repository, name)
        assert getattr(read_compare, name) is getattr(api_skills, name)
