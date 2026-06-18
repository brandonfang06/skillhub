from app.api import skills as api_skills
from app.skills import read_repository
from app.skills import read_files


def test_read_files_module_owns_file_and_download_helpers() -> None:
    assert read_files.DownloadResult is read_repository.DownloadResult
    assert read_files.DownloadResult is api_skills.DownloadResult
    assert read_files.SkillResolveError is read_repository.SkillResolveError
    assert read_files.SkillResolveError is api_skills.SkillResolveError

    for name in [
        "assert_download_access",
        "assert_version_file_content_access",
        "build_download_filename",
        "build_download_response",
        "bundle_storage_key",
        "read_bundle_or_build_fallback_zip",
        "read_file_content_from_row",
        "read_local_storage_bytes",
        "read_local_storage_text",
        "sanitize_download_filename",
    ]:
        assert getattr(read_files, name) is getattr(read_repository, name)
        assert getattr(read_files, name) is getattr(api_skills, name)
