from io import BytesIO
from stat import S_IFLNK
from zipfile import ZipFile, ZipInfo

import pytest

from app.repository_imports.archive import (
    RepositoryArchiveError,
    RepositoryArchiveLimits,
    read_repository_archive,
)


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_archive_limits_default_to_the_operator_contract() -> None:
    assert RepositoryArchiveLimits() == RepositoryArchiveLimits(
        max_file_count=500,
        max_single_file_bytes=5 * 1024 * 1024,
        max_total_bytes=50 * 1024 * 1024,
    )


def test_archive_normalizes_one_gitlab_root_directory() -> None:
    files = read_repository_archive(
        make_zip(
            {
                "project-deadbeef/skills/alpha/SKILL.md": b"---\nname: alpha\n---",
                "project-deadbeef/skills/alpha/main.py": b"print('safe')",
            }
        )
    )

    assert [item.path for item in files] == [
        "skills/alpha/SKILL.md",
        "skills/alpha/main.py",
    ]


@pytest.mark.parametrize(
    "path",
    ["../escape.txt", "/absolute.txt", "root/../../escape.txt", "C:/escape.txt"],
)
def test_archive_rejects_traversal_and_absolute_paths(path: str) -> None:
    with pytest.raises(RepositoryArchiveError, match="unsafePath"):
        read_repository_archive(make_zip({path: b"x"}))


def test_archive_rejects_symlink_entries() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        info = ZipInfo("root/link")
        info.create_system = 3
        info.external_attr = (S_IFLNK | 0o777) << 16
        archive.writestr(info, b"target")

    with pytest.raises(RepositoryArchiveError, match="symlink"):
        read_repository_archive(buffer.getvalue())


def test_archive_rejects_duplicate_normalized_paths_and_limits() -> None:
    duplicate = BytesIO()
    with ZipFile(duplicate, "w") as archive:
        archive.writestr("root/a.txt", b"a")
        archive.writestr("root/a.txt", b"b")
    with pytest.raises(RepositoryArchiveError, match="duplicatePath"):
        read_repository_archive(duplicate.getvalue())

    with pytest.raises(RepositoryArchiveError, match="fileTooLarge"):
        read_repository_archive(
            make_zip({"root/a.txt": b"1234"}),
            RepositoryArchiveLimits(max_single_file_bytes=3),
        )
    with pytest.raises(RepositoryArchiveError, match="tooManyFiles"):
        read_repository_archive(
            make_zip({"root/a.txt": b"a", "root/b.txt": b"b"}),
            RepositoryArchiveLimits(max_file_count=1),
        )
    with pytest.raises(RepositoryArchiveError, match="expandedTooLarge"):
        read_repository_archive(
            make_zip({"root/a.txt": b"aa", "root/b.txt": b"bb"}),
            RepositoryArchiveLimits(max_total_bytes=3),
        )
